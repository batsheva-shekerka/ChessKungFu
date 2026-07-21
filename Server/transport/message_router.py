from __future__ import annotations

from typing import Any, Optional

from application.auth_service import AuthService
from application.game_service import GameService
from application.matchmaking_service import MatchmakingService
from application.room_service import RoomService
from domain.models import PlayerRole
from domain import events
from infrastructure.async_event_bus import AsyncEventBus
from infrastructure.db.user_repository import UserRepository
from infrastructure.logging.error_logger import ServerLogger
from protocol import (
    MSG_AUTH,
    MSG_CANCEL_PLAY,
    MSG_LOGIN,
    MSG_MOVE,
    MSG_PLAY,
    MSG_ROOM_CREATE,
    MSG_ROOM_JOIN,
    ProtocolError,
    decode,
    encode,
    make_ack,
    make_auth_ok,
    make_error,
    make_login_ok,
    make_welcome,
    parse_auth,
    parse_login,
    parse_move,
    parse_room_join,
)
from transport.connection_registry import ConnectionContext, ConnectionRegistry


class MessageRouter:
    def __init__(
        self,
        auth: AuthService,
        rooms: RoomService,
        games: GameService,
        matchmaking: MatchmakingService,
        registry: ConnectionRegistry,
        users: UserRepository,
        bus: AsyncEventBus,
        logger: ServerLogger,
    ):
        self._auth = auth
        self._rooms = rooms
        self._games = games
        self._mm = matchmaking
        self._registry = registry
        self._users = users
        self._bus = bus
        self._logger = logger

    async def handle_raw(self, ctx: ConnectionContext, raw: str) -> None:
        try:
            data = decode(raw)
        except ProtocolError as exc:
            await ctx.websocket.send(encode(make_error(str(exc))))
            return

        msg_type = data["type"]
        try:
            await self._dispatch(ctx, msg_type, data)
        except Exception as exc:
            self._logger.error(
                "Unhandled handler error",
                exc=exc,
                user_id=ctx.user_id,
                room_id=self._rooms.room_id_for_user(ctx.user_id) if ctx.user_id else None,
                msg_type=msg_type,
            )
            await ctx.websocket.send(encode(make_error("internal server error")))

    async def _dispatch(self, ctx: ConnectionContext, msg_type: str, data: dict[str, Any]) -> None:
        if msg_type == MSG_LOGIN:
            await self._on_login(ctx, data)
            return
        if msg_type == MSG_AUTH:
            await self._on_auth(ctx, data)
            return

        if not ctx.authenticated:
            await ctx.websocket.send(encode(make_error("please login first")))
            return

        if msg_type == MSG_PLAY:
            await self._on_play(ctx)
        elif msg_type == MSG_CANCEL_PLAY:
            await self._on_cancel_play(ctx)
        elif msg_type == MSG_ROOM_CREATE:
            await self._on_room_create(ctx)
        elif msg_type == MSG_ROOM_JOIN:
            await self._on_room_join(ctx, data)
        elif msg_type == MSG_MOVE:
            await self._on_move(ctx, data)
        else:
            await ctx.websocket.send(encode(make_error(f"unknown message type: {msg_type}")))

    async def _on_login(self, ctx: ConnectionContext, data: dict[str, Any]) -> None:
        if ctx.authenticated:
            await ctx.websocket.send(encode(make_error("already logged in")))
            return
        try:
            username, password = parse_login(data)
        except ProtocolError as exc:
            await ctx.websocket.send(encode(make_error(str(exc))))
            return

        result = self._auth.login(username, password)
        if not result.ok or result.user is None or result.token is None:
            await ctx.websocket.send(encode(make_error(result.reason)))
            return

        user = result.user
        self._registry.bind_user(ctx, user.user_id, user.username, user.elo, result.token)

        # Reconnect into existing room if any
        room_id = self._rooms.reconnect(user.user_id)
        await ctx.websocket.send(
            encode(
                make_login_ok(
                    username=user.username,
                    elo=user.elo,
                    user_id=user.user_id,
                    token=result.token,
                )
            )
        )
        if room_id:
            role = self._rooms.member_role(room_id, user.user_id)
            color = role.value if role and role != PlayerRole.VIEWER else "viewer"
            await ctx.websocket.send(
                encode({
                    "type": "rejoined_room",
                    "room_id": room_id,
                    "color": color,
                })
            )
            self._logger.info("User re-authenticated into room", user_id=user.user_id, room_id=room_id)
        else:
            self._logger.info("User logged in", user_id=user.user_id, username=user.username)

    async def _on_auth(self, ctx: ConnectionContext, data: dict[str, Any]) -> None:
        try:
            token = parse_auth(data)
        except ProtocolError as exc:
            await ctx.websocket.send(encode(make_error(str(exc))))
            return
        user = self._auth.authenticate(token)
        if user is None:
            await ctx.websocket.send(encode(make_error("invalid or expired token")))
            return
        self._registry.bind_user(ctx, user.user_id, user.username, user.elo, token)
        room_id = self._rooms.reconnect(user.user_id)
        await ctx.websocket.send(
            encode(make_auth_ok(user_id=user.user_id, username=user.username, elo=user.elo))
        )
        if room_id:
            role = self._rooms.member_role(room_id, user.user_id)
            color = role.value if role and role != PlayerRole.VIEWER else "viewer"
            await ctx.websocket.send(
                encode({"type": "rejoined_room", "room_id": room_id, "color": color})
            )

    async def _on_play(self, ctx: ConnectionContext) -> None:
        assert ctx.user_id
        if self._rooms.room_id_for_user(ctx.user_id):
            await ctx.websocket.send(encode(make_error("already in a room")))
            return
        status = self._mm.enqueue(ctx.user_id)
        await ctx.websocket.send(encode({"type": "play_queued", "status": status}))

    async def _on_cancel_play(self, ctx: ConnectionContext) -> None:
        assert ctx.user_id
        cancelled = self._mm.cancel(ctx.user_id)
        await ctx.websocket.send(
            encode({"type": "play_cancelled", "cancelled": cancelled})
        )

    async def _on_room_create(self, ctx: ConnectionContext) -> None:
        assert ctx.user_id
        try:
            room = self._rooms.create_room(ctx.user_id)
        except ValueError as exc:
            await ctx.websocket.send(encode(make_error(str(exc))))
            return
        await ctx.websocket.send(
            encode({
                "type": "room_created",
                "room_id": room.room_id,
                "color": "w",
                "player_count": 1,
            })
        )

    async def _on_room_join(self, ctx: ConnectionContext, data: dict[str, Any]) -> None:
        assert ctx.user_id
        try:
            room_id = parse_room_join(data)
            room, role = self._rooms.join_room(room_id, ctx.user_id)
        except (ProtocolError, ValueError) as exc:
            await ctx.websocket.send(encode(make_error(str(exc))))
            return

        color = role.value if role != PlayerRole.VIEWER else "viewer"
        players = len([
            m for m in room.members.values()
            if m.role in (PlayerRole.WHITE, PlayerRole.BLACK)
        ])
        msg = make_welcome(color=color if color != "viewer" else "w", player_count=players)
        msg["type"] = "room_joined"
        msg["room_id"] = room.room_id
        msg["role"] = role.value
        await ctx.websocket.send(encode(msg))

        # Notify room about new player
        await self._broadcast_room_members(
            room.room_id,
            encode({
                "type": "room_update",
                "room_id": room.room_id,
                "player_count": players,
                "joined": ctx.user_id,
                "role": role.value,
            }),
        )

    async def _on_move(self, ctx: ConnectionContext, data: dict[str, Any]) -> None:
        assert ctx.user_id
        room_id = self._rooms.room_id_for_user(ctx.user_id)
        if room_id is None:
            await ctx.websocket.send(encode(make_error("not in a room")))
            return
        role = self._rooms.member_role(room_id, ctx.user_id)
        if role is None or role == PlayerRole.VIEWER:
            await ctx.websocket.send(encode(make_error("viewers cannot move")))
            return

        try:
            start, end = parse_move(data)
        except ProtocolError as exc:
            await ctx.websocket.send(encode(make_error(str(exc))))
            return

        color = "w" if role == PlayerRole.WHITE else "b"
        ok, reason = self._games.handle_move(room_id, ctx.user_id, color, start, end)
        if not ok:
            await ctx.websocket.send(encode(make_error(reason)))
            return

        await self._bus.publish(
            events.PLAYER_MOVE,
            room_id=room_id,
            user_id=ctx.user_id,
            start=start,
            end=end,
        )
        await self._broadcast_room_members(
            room_id, encode(make_ack(start, end, accepted=True) | {"room_id": room_id})
        )

    async def _broadcast_room_members(self, room_id: str, message: str) -> None:
        room = self._rooms.get_room(room_id)
        if room is None:
            return
        await self._registry.broadcast_users(list(room.members.keys()), message)

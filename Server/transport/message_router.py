from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Optional

from application.dto import CommandOutcome, SessionOutcome
from application.lobby_service import LobbyService
from application.ports import AppLogger
from application.session_service import SessionService
from application.game_service import GameService
from protocol import (
    MessageType,
    ProtocolError,
    RejoinedRoomMessage,
    AckMessage,
    decode,
    encode,
    make_auth_ok,
    make_error,
    make_login_ok,
    parse_auth,
    parse_login,
    parse_move,
    parse_room_join,
)
from transport.connection_registry import ConnectionContext, ConnectionRegistry

Handler = Callable[[ConnectionContext, dict[str, Any]], Awaitable[None]]


class MessageRouter:
    """
    Thin transport adapter: decode protocol -> application use-case -> encode/send.
    No infrastructure imports; no game/room business rules.
    """

    def __init__(
        self,
        sessions: SessionService,
        lobby: LobbyService,
        games: GameService,
        registry: ConnectionRegistry,
        logger: AppLogger,
    ):
        self._sessions = sessions
        self._lobby = lobby
        self._games = games
        self._registry = registry
        self._logger = logger
        self._public_handlers: dict[str, Handler] = {
            MessageType.LOGIN.value: self._on_login,
            MessageType.AUTH.value: self._on_auth,
        }
        self._authed_handlers: dict[str, Handler] = {
            MessageType.PLAY.value: self._on_play,
            MessageType.CANCEL_PLAY.value: self._on_cancel_play,
            MessageType.ROOM_CREATE.value: self._on_room_create,
            MessageType.ROOM_JOIN.value: self._on_room_join,
            MessageType.MOVE.value: self._on_move,
        }

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
                msg_type=msg_type,
            )
            await ctx.websocket.send(encode(make_error("internal server error")))

    async def _dispatch(
        self, ctx: ConnectionContext, msg_type: str, data: dict[str, Any]
    ) -> None:
        public = self._public_handlers.get(msg_type)
        if public is not None:
            await public(ctx, data)
            return

        if not ctx.authenticated or not ctx.user_id:
            await ctx.websocket.send(encode(make_error("please login first")))
            return

        handler = self._authed_handlers.get(msg_type)
        if handler is None:
            await ctx.websocket.send(
                encode(make_error(f"unknown message type: {msg_type}"))
            )
            return
        await handler(ctx, data)

    async def _on_login(self, ctx: ConnectionContext, data: dict[str, Any]) -> None:
        if ctx.authenticated:
            await ctx.websocket.send(encode(make_error("already logged in")))
            return
        try:
            username, password = parse_login(data)
        except ProtocolError as exc:
            await ctx.websocket.send(encode(make_error(str(exc))))
            return

        outcome = self._sessions.login(username, password)
        await self._apply_session(ctx, outcome, is_login=True)

    async def _on_auth(self, ctx: ConnectionContext, data: dict[str, Any]) -> None:
        try:
            token = parse_auth(data)
        except ProtocolError as exc:
            await ctx.websocket.send(encode(make_error(str(exc))))
            return
        outcome = self._sessions.authenticate(token)
        await self._apply_session(ctx, outcome, is_login=False)

    async def _on_play(self, ctx: ConnectionContext, data: dict[str, Any]) -> None:
        assert ctx.user_id
        await self._send_command_outcome(ctx, self._lobby.play(ctx.user_id))

    async def _on_cancel_play(
        self, ctx: ConnectionContext, data: dict[str, Any]
    ) -> None:
        assert ctx.user_id
        await self._send_command_outcome(ctx, self._lobby.cancel_play(ctx.user_id))

    async def _on_room_create(
        self, ctx: ConnectionContext, data: dict[str, Any]
    ) -> None:
        assert ctx.user_id
        await self._send_command_outcome(ctx, self._lobby.create_room(ctx.user_id))

    async def _on_room_join(
        self, ctx: ConnectionContext, data: dict[str, Any]
    ) -> None:
        assert ctx.user_id
        try:
            room_id = parse_room_join(data)
        except ProtocolError as exc:
            await ctx.websocket.send(encode(make_error(str(exc))))
            return
        await self._send_command_outcome(
            ctx, self._lobby.join_room(ctx.user_id, room_id)
        )

    async def _apply_session(
        self, ctx: ConnectionContext, outcome: SessionOutcome, *, is_login: bool
    ) -> None:
        if not outcome.ok:
            await ctx.websocket.send(encode(make_error(outcome.reason)))
            return

        assert outcome.user_id and outcome.username is not None
        assert outcome.elo is not None and outcome.token
        self._registry.bind_user(
            ctx,
            outcome.user_id,
            outcome.username,
            outcome.elo,
            outcome.token,
        )

        if is_login:
            await ctx.websocket.send(
                encode(
                    make_login_ok(
                        username=outcome.username,
                        elo=outcome.elo,
                        user_id=outcome.user_id,
                        token=outcome.token,
                    )
                )
            )
        else:
            await ctx.websocket.send(
                encode(
                    make_auth_ok(
                        user_id=outcome.user_id,
                        username=outcome.username,
                        elo=outcome.elo,
                    )
                )
            )

        if outcome.rejoin_room_id:
            await ctx.websocket.send(
                encode(
                    RejoinedRoomMessage(
                        room_id=outcome.rejoin_room_id,
                        color=outcome.rejoin_color,
                    )
                )
            )

    async def _on_move(self, ctx: ConnectionContext, data: dict[str, Any]) -> None:
        assert ctx.user_id
        try:
            start, end = parse_move(data)
        except ProtocolError as exc:
            await ctx.websocket.send(encode(make_error(str(exc))))
            return

        outcome = await self._games.submit_move(ctx.user_id, start, end)
        if not outcome.ok:
            await ctx.websocket.send(encode(make_error(outcome.reason)))
            return

        assert outcome.room_id and outcome.start and outcome.end
        ack = AckMessage(
            start=outcome.start,
            end=outcome.end,
            accepted=True,
            room_id=outcome.room_id,
        )
        await self._registry.broadcast_users(outcome.member_ids, encode(ack))

    async def _send_command_outcome(
        self, ctx: ConnectionContext, outcome: CommandOutcome
    ) -> None:
        if not outcome.ok:
            await ctx.websocket.send(encode(make_error(outcome.reason)))
            return
        await ctx.websocket.send(encode(outcome.payload))
        if outcome.broadcast_payload and outcome.broadcast_user_ids:
            await self._registry.broadcast_users(
                outcome.broadcast_user_ids,
                encode(outcome.broadcast_payload),
            )

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import websockets

from application.game_service import GameService
from protocol import encode, make_error
from transport.connection_registry import ConnectionRegistry

if TYPE_CHECKING:
    from transport.message_router import MessageRouter
    from application.room_service import RoomService
    from application.matchmaking_service import MatchmakingService
    from infrastructure.logging.error_logger import ServerLogger
    from infrastructure.db.user_repository import UserRepository


class WebSocketServerApp:
    def __init__(
        self,
        host: str,
        port: int,
        registry: ConnectionRegistry,
        router: "MessageRouter",
        rooms: "RoomService",
        matchmaking: "MatchmakingService",
        games: "GameService",
        users: "UserRepository",
        logger: "ServerLogger",
        encode_fn,
        make_game_over_fn,
        make_disconnect_countdown_fn,
    ):
        self._host = host
        self._port = port
        self._registry = registry
        self._router = router
        self._rooms = rooms
        self._mm = matchmaking
        self._games = games
        self._users = users
        self._logger = logger
        self._encode = encode_fn
        self._make_game_over = make_game_over_fn
        self._make_disconnect_countdown = make_disconnect_countdown_fn
        self._last_countdown_sent: dict[str, int] = {}

    async def handle_client(self, websocket):
        ctx = self._registry.add(websocket)
        self._logger.info("Client connected")
        try:
            async for raw in websocket:
                await self._router.handle_raw(ctx, raw)
        except websockets.exceptions.ConnectionClosed:
            self._logger.info("Client connection closed", user_id=ctx.user_id)
        except Exception as exc:
            self._logger.error("Connection error", exc=exc, user_id=ctx.user_id)
            try:
                await websocket.send(encode(make_error("connection error")))
            except Exception:
                pass
        finally:
            removed = self._registry.remove(websocket)
            if removed and removed.user_id:
                self._mm.cancel(removed.user_id)
                room_id = self._rooms.mark_disconnected(removed.user_id)
                if room_id:
                    await self._registry.broadcast_users(
                        list(self._rooms.get_room(room_id).members.keys())
                        if self._rooms.get_room(room_id)
                        else [],
                        self._encode(
                            self._make_disconnect_countdown(
                                room_id=room_id,
                                user_id=removed.user_id,
                                seconds_left=20,
                            )
                        ),
                    )

    async def background_loop(self):
        while True:
            try:
                await self._mm.tick()
                await self._games.tick_all(self._encode, self._make_game_over)
                await self._process_disconnect_grace()
            except Exception as exc:
                self._logger.error("Background loop error", exc=exc)
            await asyncio.sleep(GameService.TICK_MS / 1000)

    async def _process_disconnect_grace(self):
        for room_id, user_id, seconds_left in self._rooms.disconnect_countdowns():
            key = f"{room_id}:{user_id}"
            prev = self._last_countdown_sent.get(key)
            if prev != seconds_left:
                self._last_countdown_sent[key] = seconds_left
                room = self._rooms.get_room(room_id)
                if room:
                    await self._registry.broadcast_users(
                        list(room.members.keys()),
                        self._encode(
                            self._make_disconnect_countdown(
                                room_id=room_id,
                                user_id=user_id,
                                seconds_left=seconds_left,
                            )
                        ),
                    )

        for room_id, user_id in self._rooms.expired_disconnects():
            self._logger.info("Disconnect grace expired - forfeit", room_id=room_id, user_id=user_id)
            await self._games.force_forfeit(
                room_id, user_id, self._encode, self._make_game_over
            )
            # clear deadline so we don't repeat
            room = self._rooms.get_room(room_id)
            if room and user_id in room.members:
                room.members[user_id].disconnect_deadline = None
            self._last_countdown_sent.pop(f"{room_id}:{user_id}", None)

    async def run(self):
        async with websockets.serve(self.handle_client, self._host, self._port):
            self._logger.info(
                f"WebSocket server listening on ws://{self._host}:{self._port}"
            )
            asyncio.create_task(self.background_loop())
            await asyncio.Future()

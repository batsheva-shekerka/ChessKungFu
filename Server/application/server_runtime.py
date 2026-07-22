from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from application.game_service import GameService
from application.matchmaking_service import MatchmakingService
from application.ports import AppLogger
from application.room_service import DISCONNECT_GRACE_SECONDS, RoomService


BroadcastUsersFn = Callable[[list[str], str], Awaitable[None]]


class ServerRuntime:
    """
    Application-layer orchestrator: matchmaking ticks, game clock,
    and disconnect-grace / forfeit — not transport concerns.
    """

    def __init__(
        self,
        *,
        matchmaking: MatchmakingService,
        games: GameService,
        rooms: RoomService,
        logger: AppLogger,
        broadcast_users: BroadcastUsersFn,
        encode_fn: Callable[[dict[str, Any]], str],
        make_game_over_fn: Callable[..., dict[str, Any]],
        make_disconnect_countdown_fn: Callable[..., dict[str, Any]],
    ):
        self._mm = matchmaking
        self._games = games
        self._rooms = rooms
        self._logger = logger
        self._broadcast_users = broadcast_users
        self._encode = encode_fn
        self._make_game_over = make_game_over_fn
        self._make_disconnect_countdown = make_disconnect_countdown_fn
        self._last_countdown_sent: dict[str, int] = {}

    async def on_client_disconnected(self, user_id: str) -> None:
        self._mm.cancel(user_id)
        room_id = self._rooms.mark_disconnected(user_id)
        if not room_id:
            return
        room = self._rooms.get_room(room_id)
        if room is None:
            return
        await self._broadcast_users(
            list(room.members.keys()),
            self._encode(
                self._make_disconnect_countdown(
                    room_id=room_id,
                    user_id=user_id,
                    seconds_left=DISCONNECT_GRACE_SECONDS,
                )
            ),
        )

    async def run(self) -> None:
        while True:
            try:
                await self._mm.tick()
                await self._games.tick_all(self._encode, self._make_game_over)
                await self._process_disconnect_grace()
            except Exception as exc:
                self._logger.error("Background loop error", exc=exc)
            await asyncio.sleep(GameService.TICK_MS / 1000)

    async def _process_disconnect_grace(self) -> None:
        for room_id, user_id, seconds_left in self._rooms.disconnect_countdowns():
            key = f"{room_id}:{user_id}"
            if self._last_countdown_sent.get(key) == seconds_left:
                continue
            self._last_countdown_sent[key] = seconds_left
            room = self._rooms.get_room(room_id)
            if room is None:
                continue
            await self._broadcast_users(
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
            self._logger.info(
                "Disconnect grace expired - forfeit",
                room_id=room_id,
                user_id=user_id,
            )
            await self._games.force_forfeit(
                room_id, user_id, self._encode, self._make_game_over
            )
            self._rooms.clear_disconnect_deadline(room_id, user_id)
            self._last_countdown_sent.pop(f"{room_id}:{user_id}", None)

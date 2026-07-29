"""Matchmaker worker process: reads Redis queue, allocates shard, notifies gateway."""

from __future__ import annotations

import secrets
import time
from typing import Callable

from application.matchmaking_service import ELO_WINDOW, QUEUE_TIMEOUT_SECONDS
from application.ports import AppLogger
from infrastructure.matchmaking.allocator import GameAllocator
from infrastructure.matchmaking.redis_queue import RedisMatchmakingQueue


class RedisMatchmakerWorker:
    def __init__(
        self,
        queue: RedisMatchmakingQueue,
        allocator: GameAllocator,
        logger: AppLogger,
        get_elo: Callable[[str], int] | None = None,
    ):
        self._queue = queue
        self._allocator = allocator
        self._logger = logger
        self._get_elo = get_elo

    async def tick(self) -> None:
        await self._expire_timeouts()
        await self._try_match()

    async def _expire_timeouts(self) -> None:
        now = time.time()
        timed_out: list[str] = []
        for entry in self._queue.snapshot():
            if now - entry.enqueued_at >= QUEUE_TIMEOUT_SECONDS:
                timed_out.append(entry.user_id)
                self._queue.publish_event(
                    {
                        "type": "match_timeout",
                        "user_id": entry.user_id,
                        "reason": "no opponent within 60 seconds",
                    }
                )
                self._logger.info("Matchmaking timeout", user_id=entry.user_id)
        if timed_out:
            self._queue.remove_users(timed_out)

    async def _try_match(self) -> None:
        queue = self._queue.snapshot()
        used: set[str] = set()
        i = 0
        while i < len(queue):
            a = queue[i]
            if a.user_id in used:
                i += 1
                continue
            match = None
            for j in range(i + 1, len(queue)):
                b = queue[j]
                if b.user_id in used:
                    continue
                if abs(a.elo - b.elo) <= ELO_WINDOW:
                    match = b
                    break
            if match is None:
                i += 1
                continue

            used.add(a.user_id)
            used.add(match.user_id)
            room_id = secrets.token_hex(3)
            shard_id = self._allocator.allocate(room_id)
            self._queue.publish_event(
                {
                    "type": "create_match",
                    "room_id": room_id,
                    "white_id": a.user_id,
                    "black_id": match.user_id,
                    "shard_id": shard_id,
                }
            )
            self._logger.info(
                "Match found (remote matchmaker)",
                room_id=room_id,
                white=a.user_id,
                black=match.user_id,
                shard_id=shard_id,
            )
            i += 1

        if used:
            self._queue.remove_users(list(used))

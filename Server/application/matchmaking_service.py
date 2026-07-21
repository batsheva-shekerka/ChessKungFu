from __future__ import annotations

import time
from typing import Any, Callable, Optional

from domain.models import QueueEntry
from infrastructure.logging.error_logger import ServerLogger

ELO_WINDOW = 100
QUEUE_TIMEOUT_SECONDS = 60


class MatchmakingService:
    def __init__(
        self,
        logger: ServerLogger,
        create_matched_room: Callable[[str, str], Any],
        notify_user: Callable[[str, dict], Any],
        get_elo: Callable[[str], int],
    ):
        self._queue: list[QueueEntry] = []
        self._logger = logger
        self._create_matched_room = create_matched_room
        self._notify_user = notify_user
        self._get_elo = get_elo

    def enqueue(self, user_id: str) -> str:
        if any(e.user_id == user_id for e in self._queue):
            return "already_queued"
        elo = self._get_elo(user_id)
        self._queue.append(QueueEntry(user_id=user_id, elo=elo, enqueued_at=time.time()))
        self._logger.info("Queued for matchmaking", user_id=user_id, elo=elo)
        return "queued"

    def cancel(self, user_id: str) -> bool:
        before = len(self._queue)
        self._queue = [e for e in self._queue if e.user_id != user_id]
        return len(self._queue) < before

    def is_queued(self, user_id: str) -> bool:
        return any(e.user_id == user_id for e in self._queue)

    async def tick(self) -> None:
        await self._expire_timeouts()
        await self._try_match()

    async def _expire_timeouts(self) -> None:
        now = time.time()
        still: list[QueueEntry] = []
        for entry in self._queue:
            if now - entry.enqueued_at >= QUEUE_TIMEOUT_SECONDS:
                await self._notify_user(
                    entry.user_id,
                    {"type": "match_timeout", "reason": "no opponent within 60 seconds"},
                )
                self._logger.info("Matchmaking timeout", user_id=entry.user_id)
            else:
                still.append(entry)
        self._queue = still

    async def _try_match(self) -> None:
        used: set[str] = set()
        i = 0
        while i < len(self._queue):
            a = self._queue[i]
            if a.user_id in used:
                i += 1
                continue
            match: Optional[QueueEntry] = None
            for j in range(i + 1, len(self._queue)):
                b = self._queue[j]
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
            room = self._create_matched_room(a.user_id, match.user_id)
            payload = {
                "type": "match_found",
                "room_id": room.room_id,
                "players": {
                    "w": a.user_id,
                    "b": match.user_id,
                },
            }
            await self._notify_user(a.user_id, {**payload, "color": "w"})
            await self._notify_user(match.user_id, {**payload, "color": "b"})
            self._logger.info(
                "Match found",
                room_id=room.room_id,
                white=a.user_id,
                black=match.user_id,
            )
            i += 1

        self._queue = [e for e in self._queue if e.user_id not in used]

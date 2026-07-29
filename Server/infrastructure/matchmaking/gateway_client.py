"""
Remote matchmaking façade for the gateway (enqueue/cancel only).
Matching itself runs in the dedicated matchmaker service.
"""

from __future__ import annotations

from typing import Callable

from application.ports import AppLogger
from infrastructure.matchmaking.redis_queue import RedisMatchmakingQueue


class RedisMatchmakingGateway:
    """Same surface LobbyService needs: enqueue / cancel / is_queued / tick(no-op)."""

    def __init__(
        self,
        queue: RedisMatchmakingQueue,
        get_elo: Callable[[str], int],
        logger: AppLogger,
    ):
        self._queue = queue
        self._get_elo = get_elo
        self._logger = logger

    def enqueue(self, user_id: str) -> str:
        elo = self._get_elo(user_id)
        status = self._queue.enqueue(user_id, elo)
        self._logger.info("Queued for matchmaking (redis)", user_id=user_id, elo=elo)
        return status

    def cancel(self, user_id: str) -> bool:
        return self._queue.cancel(user_id)

    def is_queued(self, user_id: str) -> bool:
        return self._queue.is_queued(user_id)

    async def tick(self) -> None:
        # Matching is handled by the matchmaker service.
        return

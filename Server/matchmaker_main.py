"""Dedicated matchmaker service entrypoint (SERVICE_ROLE=matchmaker)."""

from __future__ import annotations

import asyncio
import os
import sys

SERVER_ROOT = os.path.dirname(os.path.abspath(__file__))
if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)

from bootstrap.logging_setup import create_server_logger
from bootstrap.wiring import _build_user_store
from infrastructure.matchmaking.allocator import GameAllocator
from infrastructure.matchmaking.redis_queue import RedisMatchmakingQueue
from infrastructure.matchmaking.worker import RedisMatchmakerWorker


async def main() -> None:
    logger = create_server_logger(SERVER_ROOT)
    redis_url = os.environ.get("REDIS_URL", "").strip()
    if not redis_url:
        raise SystemExit("REDIS_URL is required for the matchmaker service")

    db_path = os.path.join(SERVER_ROOT, "users.db")
    users = _build_user_store(db_path, logger)

    def get_elo(user_id: str) -> int:
        user = users.get_by_id(user_id)
        return user.elo if user else 1200

    shards = [
        s.strip()
        for s in os.environ.get("GAME_SHARDS", "ws-gateway").split(",")
        if s.strip()
    ]
    queue = RedisMatchmakingQueue(redis_url)
    allocator = GameAllocator(redis_url, shard_ids=shards)
    worker = RedisMatchmakerWorker(
        queue=queue,
        allocator=allocator,
        logger=logger,
        get_elo=get_elo,
    )
    logger.info("Matchmaker service started", shards=shards)
    while True:
        try:
            await worker.tick()
        except Exception as exc:
            logger.error("Matchmaker tick error", exc=exc)
        await asyncio.sleep(0.2)


if __name__ == "__main__":
    asyncio.run(main())

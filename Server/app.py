"""Minimal entry point for the KungFu Chess WebSocket gateway / monolith."""

from __future__ import annotations

import asyncio
import os
import sys

SERVER_ROOT = os.path.dirname(os.path.abspath(__file__))
if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)

from bootstrap.wiring import create_app
from infrastructure.matchmaking.event_listener import run_matchmaker_event_listener


async def main() -> None:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8765"))
    container = create_app(host=host, port=port)
    asyncio.create_task(container.runtime.run())
    if container.use_remote_matchmaker and container.redis_url:
        asyncio.create_task(
            run_matchmaker_event_listener(
                redis_url=container.redis_url,
                rooms=container.rooms,
                games=container.games,
                registry=container.registry,
                logger=container.logger,
            )
        )
        container.logger.info("Started matchmaker event listener on gateway")
    await container.server.run()


if __name__ == "__main__":
    asyncio.run(main())

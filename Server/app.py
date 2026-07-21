"""Minimal entry point for the KungFu Chess server."""

from __future__ import annotations

import asyncio
import os
import sys

SERVER_ROOT = os.path.dirname(os.path.abspath(__file__))
if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)

from bootstrap.wiring import create_app


async def main() -> None:
    container = create_app()
    await container.server.run()


if __name__ == "__main__":
    asyncio.run(main())

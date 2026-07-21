"""Shim — keeps `py -3 server.py` working after the architecture refactor."""

from app import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())

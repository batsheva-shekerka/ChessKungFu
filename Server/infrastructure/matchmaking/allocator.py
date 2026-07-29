"""Game Allocator — chooses which game shard owns a room."""

from __future__ import annotations

from typing import Sequence

import redis

ROOM_SHARD_KEY = "room:shard:{room_id}"


class GameAllocator:
    """
    Records room_id → shard in Redis.
    In the current Compose split the game engine still runs inside ws-gateway;
    allocator still makes the assignment explicit for scale-out later.
    """

    def __init__(self, redis_url: str, shard_ids: Sequence[str] | None = None):
        self._r = redis.from_url(redis_url, decode_responses=True)
        self._shards = list(shard_ids) if shard_ids else ["ws-gateway"]

    def allocate(self, room_id: str) -> str:
        shard = self._shards[hash(room_id) % len(self._shards)]
        self._r.set(ROOM_SHARD_KEY.format(room_id=room_id), shard)
        return shard

    def shard_for(self, room_id: str) -> str | None:
        return self._r.get(ROOM_SHARD_KEY.format(room_id=room_id))

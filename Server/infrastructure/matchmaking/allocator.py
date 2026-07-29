"""Game Allocator — chooses which game shard owns a room."""

from __future__ import annotations

from typing import Sequence

import redis

ROOM_SHARD_KEY = "room:shard:{room_id}"
USER_ROOM_KEY = "user:room:{user_id}"
SHARD_RR_KEY = "kungfu:shard:rr"


class GameAllocator:
    """
    Records room_id → shard and user_id → room in Redis.
    Gateway uses these keys to route commands to the owning game-server.
    """

    def __init__(self, redis_url: str, shard_ids: Sequence[str] | None = None):
        self._r = redis.from_url(redis_url, decode_responses=True)
        self._shards = [s for s in (shard_ids or []) if s] or ["game-server-1"]

    @property
    def shard_ids(self) -> list[str]:
        return list(self._shards)

    def allocate(self, room_id: str) -> str:
        shard = self._shards[hash(room_id) % len(self._shards)]
        self._r.set(ROOM_SHARD_KEY.format(room_id=room_id), shard)
        return shard

    def claim_room(self, room_id: str, shard_id: str) -> None:
        self._r.set(ROOM_SHARD_KEY.format(room_id=room_id), shard_id)

    def shard_for(self, room_id: str) -> str | None:
        return self._r.get(ROOM_SHARD_KEY.format(room_id=room_id))

    def bind_player(self, user_id: str, room_id: str) -> None:
        if user_id and room_id:
            self._r.set(USER_ROOM_KEY.format(user_id=user_id), room_id)

    def unbind_player(self, user_id: str) -> None:
        if user_id:
            self._r.delete(USER_ROOM_KEY.format(user_id=user_id))

    def room_for_user(self, user_id: str) -> str | None:
        return self._r.get(USER_ROOM_KEY.format(user_id=user_id))

    def shard_for_user(self, user_id: str) -> str | None:
        room_id = self.room_for_user(user_id)
        if not room_id:
            return None
        return self.shard_for(room_id)

    def pick_shard(self) -> str:
        """Round-robin shard selection (e.g. manual room_create)."""
        n = int(self._r.incr(SHARD_RR_KEY))
        return self._shards[(n - 1) % len(self._shards)]

    def bind_match(self, room_id: str, shard_id: str, user_ids: Sequence[str]) -> None:
        self.claim_room(room_id, shard_id)
        for uid in user_ids:
            self.bind_player(uid, room_id)

"""Redis-backed matchmaking queue (shared by gateway + matchmaker)."""

from __future__ import annotations

import time
from typing import Optional

import redis

from domain.models import QueueEntry

QUEUE_KEY = "mm:queue"
ELO_KEY = "mm:elo"
EVENTS_CHANNEL = "kungfu:mm:events"


class RedisMatchmakingQueue:
    def __init__(self, redis_url: str):
        self._r = redis.from_url(redis_url, decode_responses=True)
        self._r.ping()

    def enqueue(self, user_id: str, elo: int) -> str:
        if self._r.zscore(QUEUE_KEY, user_id) is not None:
            return "already_queued"
        pipe = self._r.pipeline()
        pipe.zadd(QUEUE_KEY, {user_id: time.time()})
        pipe.hset(ELO_KEY, user_id, int(elo))
        pipe.execute()
        return "queued"

    def cancel(self, user_id: str) -> bool:
        pipe = self._r.pipeline()
        pipe.zrem(QUEUE_KEY, user_id)
        pipe.hdel(ELO_KEY, user_id)
        removed, _ = pipe.execute()
        return bool(removed)

    def is_queued(self, user_id: str) -> bool:
        return self._r.zscore(QUEUE_KEY, user_id) is not None

    def snapshot(self) -> list[QueueEntry]:
        rows = self._r.zrange(QUEUE_KEY, 0, -1, withscores=True)
        if not rows:
            return []
        elos = self._r.hgetall(ELO_KEY)
        entries: list[QueueEntry] = []
        for user_id, enqueued_at in rows:
            elo_raw = elos.get(user_id, "1200")
            try:
                elo = int(elo_raw)
            except ValueError:
                elo = 1200
            entries.append(
                QueueEntry(
                    user_id=user_id,
                    elo=elo,
                    enqueued_at=float(enqueued_at),
                )
            )
        return entries

    def remove_users(self, user_ids: list[str]) -> None:
        if not user_ids:
            return
        pipe = self._r.pipeline()
        pipe.zrem(QUEUE_KEY, *user_ids)
        pipe.hdel(ELO_KEY, *user_ids)
        pipe.execute()

    def publish_event(self, payload: dict) -> None:
        import json

        self._r.publish(EVENTS_CHANNEL, json.dumps(payload, ensure_ascii=False))

    def pubsub(self):
        return self._r.pubsub(ignore_subscribe_messages=True)

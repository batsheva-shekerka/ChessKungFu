"""Redis-backed SessionStore — temporary auth tokens for scalable sessions."""

from __future__ import annotations

import json
import time
from typing import Optional

import redis

from domain.models import Session
from infrastructure.db.session_repository import DEFAULT_TTL_SECONDS


class RedisSessionRepository:
    """Implements SessionStore using Redis keys with TTL."""

    def __init__(self, redis_url: str):
        self._client = redis.from_url(redis_url, decode_responses=True)
        # Fail fast if Redis is unreachable at startup.
        self._client.ping()

    @staticmethod
    def _key(token: str) -> str:
        return f"session:{token}"

    def create(
        self,
        token: str,
        user_id: str,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> Session:
        expires_at = time.time() + ttl_seconds
        payload = json.dumps({"user_id": user_id, "expires_at": expires_at})
        self._client.setex(self._key(token), ttl_seconds, payload)
        return Session(token=token, user_id=user_id, expires_at=expires_at)

    def get_valid(self, token: str) -> Optional[Session]:
        raw = self._client.get(self._key(token))
        if raw is None:
            return None
        try:
            data = json.loads(raw)
            user_id = str(data["user_id"])
            expires_at = float(data["expires_at"])
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            self.delete(token)
            return None

        if expires_at < time.time():
            self.delete(token)
            return None
        return Session(token=token, user_id=user_id, expires_at=expires_at)

    def delete(self, token: str) -> None:
        self._client.delete(self._key(token))

"""Redis command bus: gateway ↔ game-server request/reply + outbound pushes."""

from __future__ import annotations

import json
import uuid
from typing import Any

import redis

GATEWAY_OUT_CHANNEL = "kungfu:gateway:out"


def cmd_queue_key(shard_id: str) -> str:
    return f"kungfu:game:cmdq:{shard_id}"


class GameCommandBus:
    def __init__(self, redis_url: str):
        self._r = redis.from_url(redis_url, decode_responses=True)
        self._r.ping()

    def call(
        self,
        command: dict[str, Any],
        timeout: float = 5.0,
        *,
        shard_id: str,
    ) -> dict[str, Any]:
        request_id = str(uuid.uuid4())
        reply_key = f"kungfu:reply:{request_id}"
        payload = dict(command)
        payload["request_id"] = request_id
        self._r.lpush(cmd_queue_key(shard_id), json.dumps(payload, ensure_ascii=False))
        result = self._r.blpop(reply_key, timeout=max(1, int(timeout)))
        if result is None:
            return {"ok": False, "error": "game server timeout"}
        _, raw = result
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"ok": False, "error": "invalid game server reply"}

    def reply(self, request_id: str, payload: dict[str, Any]) -> None:
        key = f"kungfu:reply:{request_id}"
        self._r.rpush(key, json.dumps(payload, ensure_ascii=False))
        self._r.expire(key, 30)

    def publish_outbound(self, user_ids: list[str], message: dict[str, Any]) -> None:
        self._r.publish(
            GATEWAY_OUT_CHANNEL,
            json.dumps(
                {"user_ids": [u for u in user_ids if u], "message": message},
                ensure_ascii=False,
            ),
        )

    def brpop_command(self, shard_id: str, timeout: int = 1):
        return self._r.brpop(cmd_queue_key(shard_id), timeout=timeout)

    def out_pubsub(self):
        return self._r.pubsub(ignore_subscribe_messages=True)

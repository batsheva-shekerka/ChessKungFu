"""Thin WebSocket gateway: auth + matchmaking enqueue + proxy to game-server."""

from __future__ import annotations

import asyncio
import json
import os
import sys

SERVER_ROOT = os.path.dirname(os.path.abspath(__file__))
if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)

from application.auth_service import AuthService
from application.session_service import SessionService
from bootstrap.logging_setup import create_server_logger
from bootstrap.wiring import _build_session_store, _build_user_store
from infrastructure.matchmaking.allocator import GameAllocator
from infrastructure.matchmaking.gateway_client import RedisMatchmakingGateway
from infrastructure.matchmaking.redis_queue import EVENTS_CHANNEL, RedisMatchmakingQueue
from infrastructure.messaging.game_bus import GATEWAY_OUT_CHANNEL, GameCommandBus
from infrastructure.messaging.remote_proxies import RemoteGameProxy, RemoteLobbyProxy
from infrastructure.observability import (
    LatencyTracker,
    check_postgres,
    check_redis,
    start_observability_server,
)
from protocol import MatchTimeoutMessage, encode
from transport.connection_registry import ConnectionRegistry
from transport.message_router import MessageRouter
from transport.websocket_server import WebSocketServerApp


class _NoRooms:
    def reconnect(self, user_id: str):
        return None


async def _outbound_listener(bus: GameCommandBus, registry: ConnectionRegistry, logger) -> None:
    pubsub = bus.out_pubsub()
    pubsub.subscribe(GATEWAY_OUT_CHANNEL)
    logger.info("Gateway listening for game outbound", channel=GATEWAY_OUT_CHANNEL)
    while True:
        message = await asyncio.to_thread(pubsub.get_message, True, 1.0)
        if not message or message.get("type") != "message":
            await asyncio.sleep(0.05)
            continue
        raw = message.get("data")
        if not isinstance(raw, str):
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        user_ids = list(data.get("user_ids") or [])
        payload = data.get("message")
        if not user_ids or not isinstance(payload, dict):
            continue
        await registry.broadcast_users(user_ids, encode(payload))


async def _mm_event_listener(redis_url: str, registry: ConnectionRegistry, logger) -> None:
    """Forward match_timeout from matchmaker (shard-agnostic)."""
    queue = RedisMatchmakingQueue(redis_url)
    pubsub = queue.pubsub()
    pubsub.subscribe(EVENTS_CHANNEL)
    while True:
        message = await asyncio.to_thread(pubsub.get_message, True, 1.0)
        if not message or message.get("type") != "message":
            await asyncio.sleep(0.05)
            continue
        raw = message.get("data")
        if not isinstance(raw, str):
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or payload.get("type") != "match_timeout":
            continue
        user_id = str(payload.get("user_id", ""))
        if not user_id:
            continue
        msg = MatchTimeoutMessage(
            reason=str(payload.get("reason", "matchmaking timeout"))
        ).to_dict()
        await registry.broadcast_users([user_id], encode(msg))
        logger.info("Matchmaking timeout forwarded", user_id=user_id)


async def main() -> None:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8765"))
    health_port = int(os.environ.get("HEALTH_PORT", "8080"))
    redis_url = os.environ.get("REDIS_URL", "").strip()
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not redis_url:
        raise SystemExit("REDIS_URL is required for ws-gateway in split mode")

    shards = [
        s.strip()
        for s in os.environ.get("GAME_SHARDS", "game-server-1").split(",")
        if s.strip()
    ]

    logger = create_server_logger(SERVER_ROOT)
    db_path = os.path.join(SERVER_ROOT, "users.db")
    users = _build_user_store(db_path, logger)
    sessions = _build_session_store(db_path, logger)
    registry = ConnectionRegistry(logger=logger)
    move_latency = LatencyTracker()

    def get_elo(user_id: str) -> int:
        user = users.get_by_id(user_id)
        return user.elo if user else 1200

    mm_queue = RedisMatchmakingQueue(redis_url)
    matchmaking = RedisMatchmakingGateway(
        queue=mm_queue, get_elo=get_elo, logger=logger
    )
    bus = GameCommandBus(redis_url)
    allocator = GameAllocator(redis_url, shard_ids=shards)
    lobby = RemoteLobbyProxy(bus, matchmaking, allocator)
    games = RemoteGameProxy(bus, allocator, move_latency=move_latency)

    auth = AuthService(users=users, sessions=sessions)
    sessions_uc = SessionService(auth=auth, rooms=_NoRooms(), logger=logger)
    router = MessageRouter(
        sessions=sessions_uc,
        lobby=lobby,
        games=games,
        registry=registry,
        logger=logger,
    )

    async def on_disconnect(user_id: str) -> None:
        matchmaking.cancel(user_id)
        shard = allocator.shard_for_user(user_id)
        if not shard:
            return
        await asyncio.to_thread(
            bus.call,
            {"type": "player_disconnected", "user_id": user_id},
            3,
            shard_id=shard,
        )

    def snapshot() -> dict:
        redis_ok = check_redis(redis_url)
        pg_ok = check_postgres(database_url)
        ok = bool(redis_ok.get("ok")) and bool(pg_ok.get("ok"))
        return {
            "ok": ok,
            "checks": {"redis": redis_ok, "postgres": pg_ok},
            "ws_connections": registry.connection_count(),
            "authenticated_users": registry.authenticated_count(),
            "matchmaking_queue_length": mm_queue.length(),
            "move_ack_latency_ms": move_latency.snapshot(),
            "shards": shards,
        }

    start_observability_server(
        host="0.0.0.0",
        port=health_port,
        service="ws-gateway",
        snapshot=snapshot,
        logger=logger,
    )

    server = WebSocketServerApp(
        host=host,
        port=port,
        registry=registry,
        router=router,
        logger=logger,
        on_client_disconnected=on_disconnect,
    )

    logger.info("Thin WS gateway started", shards=shards)
    asyncio.create_task(_outbound_listener(bus, registry, logger))
    asyncio.create_task(_mm_event_listener(redis_url, registry, logger))
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())

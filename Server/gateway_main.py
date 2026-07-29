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
from infrastructure.matchmaking.gateway_client import RedisMatchmakingGateway
from infrastructure.matchmaking.redis_queue import RedisMatchmakingQueue
from infrastructure.messaging.game_bus import GATEWAY_OUT_CHANNEL, GameCommandBus
from infrastructure.messaging.remote_proxies import RemoteGameProxy, RemoteLobbyProxy
from protocol import encode
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


async def main() -> None:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8765"))
    redis_url = os.environ.get("REDIS_URL", "").strip()
    if not redis_url:
        raise SystemExit("REDIS_URL is required for ws-gateway in split mode")

    logger = create_server_logger(SERVER_ROOT)
    db_path = os.path.join(SERVER_ROOT, "users.db")
    users = _build_user_store(db_path, logger)
    sessions = _build_session_store(db_path, logger)
    registry = ConnectionRegistry(logger=logger)

    def get_elo(user_id: str) -> int:
        user = users.get_by_id(user_id)
        return user.elo if user else 1200

    mm_queue = RedisMatchmakingQueue(redis_url)
    matchmaking = RedisMatchmakingGateway(
        queue=mm_queue, get_elo=get_elo, logger=logger
    )
    bus = GameCommandBus(redis_url)
    lobby = RemoteLobbyProxy(bus, matchmaking)
    games = RemoteGameProxy(bus)

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
        await asyncio.to_thread(
            bus.call, {"type": "player_disconnected", "user_id": user_id}, 3
        )

    server = WebSocketServerApp(
        host=host,
        port=port,
        registry=registry,
        router=router,
        logger=logger,
        on_client_disconnected=on_disconnect,
    )

    logger.info("Thin WS gateway started (game is remote)")
    asyncio.create_task(_outbound_listener(bus, registry, logger))
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())

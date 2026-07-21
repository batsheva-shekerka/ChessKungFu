from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any

SERVER_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROJECT_ROOT = os.path.abspath(os.path.join(SERVER_ROOT, ".."))

if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from application.auth_service import AuthService
from application.game_service import GameService
from application.matchmaking_service import MatchmakingService
from application.room_service import RoomService
from bootstrap.logging_setup import create_server_logger
from domain import events
from infrastructure.async_event_bus import AsyncEventBus
from infrastructure.db.session_repository import SessionRepository
from infrastructure.db.user_repository import UserRepository
from protocol import encode, make_disconnect_countdown, make_game_over
from transport.connection_registry import ConnectionRegistry
from transport.message_router import MessageRouter
from transport.websocket_server import WebSocketServerApp


@dataclass
class AppContainer:
    server: WebSocketServerApp
    logger: Any


def create_app(host: str = "localhost", port: int = 8765) -> AppContainer:
    logger = create_server_logger(SERVER_ROOT)
    db_path = os.path.join(SERVER_ROOT, "users.db")

    users = UserRepository(db_path)
    sessions = SessionRepository(db_path)
    registry = ConnectionRegistry()

    def on_bus_error(event_type: str, exc: BaseException) -> None:
        logger.error(f"Event listener failed for {event_type}", exc=exc)

    bus = AsyncEventBus(on_listener_error=on_bus_error)

    async def log_move(**payload: Any) -> None:
        logger.info("player_move", **payload)

    async def log_game_over(**payload: Any) -> None:
        logger.info("game_over", **payload)

    bus.subscribe(events.PLAYER_MOVE, log_move)
    bus.subscribe(events.GAME_OVER, log_game_over)

    games_holder: dict[str, GameService] = {}

    def on_room_created(room_id: str) -> None:
        games = games_holder["games"]
        if games.get_engine(room_id) is None:
            games.create_engine_for_room(room_id)

    async def broadcast_room(room_id: str, message: str) -> None:
        room = rooms.get_room(room_id)
        if room is None:
            return
        await registry.broadcast_users(list(room.members.keys()), message)

    async def broadcast_to_user(user_id: str, message: str) -> None:
        await registry.send_to_user(user_id, message)

    rooms = RoomService(
        logger=logger,
        on_room_created=on_room_created,
        broadcast_to_user=broadcast_to_user,
        broadcast_room=broadcast_room,
    )

    def get_room_players_for_elo(room_id: str):
        white_id, black_id = rooms.get_room_players(room_id)
        white_name = black_name = None
        if white_id:
            u = users.get_by_id(white_id)
            white_name = u.username if u else None
        if black_id:
            u = users.get_by_id(black_id)
            black_name = u.username if u else None
        return white_id, black_id, white_name, black_name

    games = GameService(
        project_root=PROJECT_ROOT,
        users=users,
        bus=bus,
        logger=logger,
        get_room_players=get_room_players_for_elo,
        is_elo_updated=rooms.is_elo_updated,
        mark_elo_updated=rooms.mark_elo_updated,
        broadcast_room=broadcast_room,
    )
    games_holder["games"] = games

    def get_elo(user_id: str) -> int:
        user = users.get_by_id(user_id)
        return user.elo if user else 1200

    async def notify_user(user_id: str, payload: dict) -> None:
        await registry.send_to_user(user_id, encode(payload))

    matchmaking = MatchmakingService(
        logger=logger,
        create_matched_room=rooms.create_matched_room,
        notify_user=notify_user,
        get_elo=get_elo,
    )

    auth = AuthService(users=users, sessions=sessions)

    router = MessageRouter(
        auth=auth,
        rooms=rooms,
        games=games,
        matchmaking=matchmaking,
        registry=registry,
        users=users,
        bus=bus,
        logger=logger,
    )

    server = WebSocketServerApp(
        host=host,
        port=port,
        registry=registry,
        router=router,
        rooms=rooms,
        matchmaking=matchmaking,
        games=games,
        users=users,
        logger=logger,
        encode_fn=encode,
        make_game_over_fn=make_game_over,
        make_disconnect_countdown_fn=make_disconnect_countdown,
    )
    return AppContainer(server=server, logger=logger)

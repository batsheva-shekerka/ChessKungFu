from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any, Optional

SERVER_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROJECT_ROOT = os.path.abspath(os.path.join(SERVER_ROOT, ".."))

if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from application.auth_service import AuthService
from application.game_service import GameService
from application.lobby_service import LobbyService
from application.matchmaking_service import MatchmakingService
from application.room_service import RoomService
from application.server_runtime import ServerRuntime
from application.session_service import SessionService
from bootstrap.logging_setup import create_server_logger
from domain.events import EventType
from infrastructure.async_event_bus import AsyncEventBus
from infrastructure.db.session_repository import SessionRepository
from infrastructure.db.redis_session_repository import RedisSessionRepository
from infrastructure.db.user_repository import UserRepository
from infrastructure.db.postgres_user_repository import PostgresUserRepository
from infrastructure.db.postgres_game_repository import PostgresGameRepository
from infrastructure.db.sqlite_game_repository import SqliteGameRepository
from infrastructure.game.board_loader import InputTxtBoardLoader
from infrastructure.game.engine_adapter import KungFuEngineFactory
from infrastructure.matchmaking.gateway_client import RedisMatchmakingGateway
from infrastructure.matchmaking.redis_queue import RedisMatchmakingQueue
from protocol import encode, make_disconnect_countdown, make_game_over
from transport.connection_registry import ConnectionRegistry
from transport.message_router import MessageRouter
from transport.websocket_server import WebSocketServerApp


@dataclass
class AppContainer:
    server: WebSocketServerApp
    runtime: ServerRuntime
    logger: Any
    redis_url: Optional[str] = None
    rooms: Any = None
    games: Any = None
    registry: Any = None
    use_remote_matchmaker: bool = False
    game_history: Any = None


def _build_session_store(db_path: str, logger: Any):
    """Prefer Redis when REDIS_URL is set; otherwise SQLite (local/dev)."""
    redis_url = os.environ.get("REDIS_URL", "").strip()
    if not redis_url:
        logger.info("Session store: SQLite", path=db_path)
        return SessionRepository(db_path)
    try:
        store = RedisSessionRepository(redis_url)
        logger.info("Session store: Redis", url=redis_url)
        return store
    except Exception as exc:
        logger.error(
            "Redis session store unavailable; falling back to SQLite",
            exc=exc,
            redis_url=redis_url,
        )
        return SessionRepository(db_path)


def _build_user_store(db_path: str, logger: Any):
    """Prefer PostgreSQL when DATABASE_URL is set; otherwise SQLite."""
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        logger.info("User store: SQLite", path=db_path)
        return UserRepository(db_path)
    try:
        store = PostgresUserRepository(database_url)
        safe = database_url.split("@")[-1] if "@" in database_url else database_url
        logger.info("User store: PostgreSQL", host=safe)
        return store
    except Exception as exc:
        logger.error(
            "PostgreSQL user store unavailable; falling back to SQLite",
            exc=exc,
        )
        return UserRepository(db_path)


def _build_game_history_store(db_path: str, logger: Any):
    """Cold-path game results: PostgreSQL when DATABASE_URL set, else SQLite."""
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        logger.info("Game history: SQLite", path=db_path)
        return SqliteGameRepository(db_path)
    try:
        store = PostgresGameRepository(database_url)
        safe = database_url.split("@")[-1] if "@" in database_url else database_url
        logger.info("Game history: PostgreSQL", host=safe)
        return store
    except Exception as exc:
        logger.error(
            "PostgreSQL game history unavailable; falling back to SQLite",
            exc=exc,
        )
        return SqliteGameRepository(db_path)


def create_app(host: str = "localhost", port: int = 8765) -> AppContainer:
    logger = create_server_logger(SERVER_ROOT)
    db_path = os.path.join(SERVER_ROOT, "users.db")
    redis_url = os.environ.get("REDIS_URL", "").strip() or None
    role = os.environ.get("SERVICE_ROLE", "all").strip().lower()
    # gateway = WS + game engine; matchmaking runs in dedicated service
    use_remote_mm = role in ("gateway", "ws-gateway") and bool(redis_url)

    users = _build_user_store(db_path, logger)
    game_history = _build_game_history_store(db_path, logger)
    sessions = _build_session_store(db_path, logger)
    registry = ConnectionRegistry(logger=logger)

    def on_bus_error(event_type: str, exc: BaseException) -> None:
        logger.error(f"Event listener failed for {event_type}", exc=exc)

    bus = AsyncEventBus(on_listener_error=on_bus_error)

    async def log_move(**payload: Any) -> None:
        logger.info("player_move", **payload)

    async def log_game_over(**payload: Any) -> None:
        logger.info("game_over", **payload)

    bus.subscribe(EventType.PLAYER_MOVE.value, log_move)
    bus.subscribe(EventType.GAME_OVER.value, log_game_over)

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

    rooms = RoomService(
        logger=logger,
        on_room_created=on_room_created,
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
        users=users,
        bus=bus,
        logger=logger,
        rooms=rooms,
        engine_factory=KungFuEngineFactory(InputTxtBoardLoader(PROJECT_ROOT)),
        get_room_players=get_room_players_for_elo,
        is_elo_updated=rooms.is_elo_updated,
        mark_elo_updated=rooms.mark_elo_updated,
        broadcast_room=broadcast_room,
        game_history=game_history,
    )
    games_holder["games"] = games

    def get_elo(user_id: str) -> int:
        user = users.get_by_id(user_id)
        return user.elo if user else 1200

    async def notify_user(user_id: str, payload: dict) -> None:
        await registry.send_to_user(user_id, encode(payload))
        if payload.get("type") == "match_found":
            room_id = payload.get("room_id")
            if room_id and games.get_engine(room_id) is not None:
                await registry.send_to_user(
                    user_id, encode(games.build_state_dict(room_id))
                )

    if use_remote_mm:
        assert redis_url is not None
        mm_queue = RedisMatchmakingQueue(redis_url)
        matchmaking = RedisMatchmakingGateway(
            queue=mm_queue, get_elo=get_elo, logger=logger
        )
        logger.info("Matchmaking: remote Redis queue (matchmaker service)")
    else:
        matchmaking = MatchmakingService(
            logger=logger,
            create_matched_room=rooms.create_matched_room,
            notify_user=notify_user,
            get_elo=get_elo,
        )
        logger.info("Matchmaking: in-process")

    auth = AuthService(users=users, sessions=sessions)
    sessions_uc = SessionService(auth=auth, rooms=rooms, logger=logger)
    lobby = LobbyService(rooms=rooms, matchmaking=matchmaking, logger=logger)

    router = MessageRouter(
        sessions=sessions_uc,
        lobby=lobby,
        games=games,
        registry=registry,
        logger=logger,
    )

    runtime = ServerRuntime(
        matchmaking=matchmaking,
        games=games,
        rooms=rooms,
        logger=logger,
        broadcast_users=registry.broadcast_users,
        encode_fn=encode,
        make_game_over_fn=make_game_over,
        make_disconnect_countdown_fn=make_disconnect_countdown,
    )

    server = WebSocketServerApp(
        host=host,
        port=port,
        registry=registry,
        router=router,
        logger=logger,
        on_client_disconnected=runtime.on_client_disconnected,
    )
    return AppContainer(
        server=server,
        runtime=runtime,
        logger=logger,
        redis_url=redis_url,
        rooms=rooms,
        games=games,
        registry=registry,
        use_remote_matchmaker=use_remote_mm,
        game_history=game_history,
    )

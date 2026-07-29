"""Game-server process: authoritative rooms/engine + Redis command worker."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

SERVER_ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SERVER_ROOT, ".."))
if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from application.game_service import GameService
from application.lobby_service import LobbyService
from application.room_service import RoomService
from application.server_runtime import ServerRuntime
from bootstrap.logging_setup import create_server_logger
from bootstrap.wiring import _build_user_store
from domain.events import EventType
from domain.models import PlayerRole
from infrastructure.async_event_bus import AsyncEventBus
from infrastructure.game.board_loader import InputTxtBoardLoader
from infrastructure.game.engine_adapter import KungFuEngineFactory
from infrastructure.matchmaking.redis_queue import EVENTS_CHANNEL, RedisMatchmakingQueue
from infrastructure.messaging.game_bus import GameCommandBus
from protocol import (
    MatchFoundMessage,
    MatchTimeoutMessage,
    encode,
    make_disconnect_countdown,
    make_game_over,
)


class _NoopMatchmaking:
    def enqueue(self, user_id: str) -> str:
        return "queued"

    def cancel(self, user_id: str) -> bool:
        return False

    async def tick(self) -> None:
        return


def _build_game_stack(logger, bus: GameCommandBus):
    db_path = os.path.join(SERVER_ROOT, "users.db")
    users = _build_user_store(db_path, logger)

    def on_bus_error(event_type: str, exc: BaseException) -> None:
        logger.error(f"Event listener failed for {event_type}", exc=exc)

    event_bus = AsyncEventBus(on_listener_error=on_bus_error)

    async def log_move(**payload: Any) -> None:
        logger.info("player_move", **payload)

    async def log_game_over(**payload: Any) -> None:
        logger.info("game_over", **payload)

    event_bus.subscribe(EventType.PLAYER_MOVE.value, log_move)
    event_bus.subscribe(EventType.GAME_OVER.value, log_game_over)

    games_holder: dict[str, GameService] = {}

    def on_room_created(room_id: str) -> None:
        games = games_holder["games"]
        if games.get_engine(room_id) is None:
            games.create_engine_for_room(room_id)

    async def broadcast_users(user_ids: list[str], message: str) -> None:
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            payload = {"type": "raw", "data": message}
        bus.publish_outbound(user_ids, payload)

    async def broadcast_room(room_id: str, message: str) -> None:
        room = rooms.get_room(room_id)
        if room is None:
            return
        await broadcast_users(list(room.members.keys()), message)

    rooms = RoomService(logger=logger, on_room_created=on_room_created)

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
        bus=event_bus,
        logger=logger,
        rooms=rooms,
        engine_factory=KungFuEngineFactory(InputTxtBoardLoader(PROJECT_ROOT)),
        get_room_players=get_room_players_for_elo,
        is_elo_updated=rooms.is_elo_updated,
        mark_elo_updated=rooms.mark_elo_updated,
        broadcast_room=broadcast_room,
    )
    games_holder["games"] = games

    lobby = LobbyService(rooms=rooms, matchmaking=_NoopMatchmaking(), logger=logger)
    runtime = ServerRuntime(
        matchmaking=_NoopMatchmaking(),
        games=games,
        rooms=rooms,
        logger=logger,
        broadcast_users=broadcast_users,
        encode_fn=encode,
        make_game_over_fn=make_game_over,
        make_disconnect_countdown_fn=make_disconnect_countdown,
    )
    return rooms, games, lobby, runtime, broadcast_users


def _handle_command(
    cmd: dict[str, Any],
    *,
    rooms: RoomService,
    games: GameService,
    lobby: LobbyService,
    bus: GameCommandBus,
    logger,
) -> dict[str, Any]:
    ctype = cmd.get("type")
    if ctype == "room_create":
        outcome = lobby.create_room(str(cmd.get("user_id", "")))
        return _outcome_to_reply(outcome, games)
    if ctype == "room_join":
        outcome = lobby.join_room(
            str(cmd.get("user_id", "")), str(cmd.get("room_id", ""))
        )
        return _outcome_to_reply(outcome, games)
    if ctype == "move":
        user_id = str(cmd.get("user_id", ""))
        start = cmd.get("start") or [0, 0]
        end = cmd.get("end") or [0, 0]
        # sync wrapper around async submit via asyncio
        return {"_async_move": True, "user_id": user_id, "start": start, "end": end}
    if ctype == "get_state":
        room_id = str(cmd.get("room_id", ""))
        if games.get_engine(room_id) is None:
            return {"ok": False, "error": "room not found"}
        return {"ok": True, "payload": games.build_state_dict(room_id)}
    if ctype == "player_disconnected":
        user_id = str(cmd.get("user_id", ""))
        return {"_async_disconnect": True, "user_id": user_id}
    logger.warning("Unknown game command", cmd=cmd)
    return {"ok": False, "error": f"unknown command: {ctype}"}


def _outcome_to_reply(outcome, games: GameService) -> dict[str, Any]:
    if not outcome.ok:
        return {"ok": False, "error": outcome.reason}
    extra: list[dict] = []
    payload = outcome.payload or {}
    room_id = payload.get("room_id")
    if room_id and games.get_engine(room_id) is not None:
        extra.append(games.build_state_dict(room_id))
    return {
        "ok": True,
        "payload": payload,
        "broadcast_user_ids": list(outcome.broadcast_user_ids or []),
        "broadcast_payload": outcome.broadcast_payload,
        "extra_payloads": extra,
    }


async def _handle_create_match(
    payload: dict[str, Any],
    *,
    rooms: RoomService,
    games: GameService,
    bus: GameCommandBus,
    logger,
) -> None:
    room_id = str(payload.get("room_id", ""))
    white_id = str(payload.get("white_id", ""))
    black_id = str(payload.get("black_id", ""))
    if not room_id or not white_id or not black_id:
        return
    try:
        room = rooms.create_matched_room(white_id, black_id, room_id=room_id)
    except ValueError as exc:
        logger.error("Failed to create matched room", exc=exc, room_id=room_id)
        return
    players = {
        PlayerRole.WHITE.value: white_id,
        PlayerRole.BLACK.value: black_id,
    }
    bus.publish_outbound(
        [white_id],
        MatchFoundMessage(
            room_id=room.room_id,
            players=players,
            color=PlayerRole.WHITE.value,
        ).to_dict(),
    )
    bus.publish_outbound(
        [black_id],
        MatchFoundMessage(
            room_id=room.room_id,
            players=players,
            color=PlayerRole.BLACK.value,
        ).to_dict(),
    )
    if games.get_engine(room.room_id) is not None:
        state = games.build_state_dict(room.room_id)
        bus.publish_outbound([white_id, black_id], state)


async def _mm_loop(mm_pubsub, rooms, games, bus, logger, shard_id: str) -> None:
    while True:
        mm_msg = await asyncio.to_thread(mm_pubsub.get_message, True, 1.0)
        if not mm_msg or mm_msg.get("type") != "message":
            await asyncio.sleep(0.05)
            continue
        raw = mm_msg.get("data")
        if not isinstance(raw, str):
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("type") == "create_match":
            target = str(payload.get("shard_id") or shard_id)
            if target != shard_id:
                continue
            await _handle_create_match(
                payload, rooms=rooms, games=games, bus=bus, logger=logger
            )
        elif payload.get("type") == "match_timeout":
            bus.publish_outbound(
                [str(payload.get("user_id", ""))],
                MatchTimeoutMessage(
                    reason=str(payload.get("reason", "matchmaking timeout"))
                ).to_dict(),
            )


async def _cmd_loop(bus, rooms, games, lobby, runtime, logger) -> None:
    while True:
        item = await asyncio.to_thread(bus.brpop_command, 1)
        if not item:
            await asyncio.sleep(0.01)
            continue
        _, raw = item
        try:
            cmd = json.loads(raw)
        except json.JSONDecodeError:
            continue
        request_id = cmd.get("request_id")
        result = _handle_command(
            cmd, rooms=rooms, games=games, lobby=lobby, bus=bus, logger=logger
        )
        if result.get("_async_move"):
            outcome = await games.submit_move(
                str(result["user_id"]),
                (int(result["start"][0]), int(result["start"][1])),
                (int(result["end"][0]), int(result["end"][1])),
            )
            if not outcome.ok:
                reply = {"ok": False, "error": outcome.reason}
            else:
                reply = {
                    "ok": True,
                    "room_id": outcome.room_id,
                    "start": list(outcome.start) if outcome.start else None,
                    "end": list(outcome.end) if outcome.end else None,
                    "member_ids": list(outcome.member_ids or []),
                }
            if request_id:
                bus.reply(str(request_id), reply)
            continue
        if result.get("_async_disconnect"):
            await runtime.on_client_disconnected(str(result["user_id"]))
            if request_id:
                bus.reply(str(request_id), {"ok": True})
            continue
        if request_id:
            bus.reply(str(request_id), result)


async def main() -> None:
    logger = create_server_logger(SERVER_ROOT)
    redis_url = os.environ.get("REDIS_URL", "").strip()
    if not redis_url:
        raise SystemExit("REDIS_URL is required for game-server")

    bus = GameCommandBus(redis_url)
    rooms, games, lobby, runtime, _broadcast_users = _build_game_stack(logger, bus)
    shard_id = os.environ.get("SHARD_ID", "game-server").strip()
    logger.info("Game server started", shard_id=shard_id)

    asyncio.create_task(runtime.run())

    mm_queue = RedisMatchmakingQueue(redis_url)
    mm_pubsub = mm_queue.pubsub()
    mm_pubsub.subscribe(EVENTS_CHANNEL)

    await asyncio.gather(
        _mm_loop(mm_pubsub, rooms, games, bus, logger, shard_id),
        _cmd_loop(bus, rooms, games, lobby, runtime, logger),
    )


if __name__ == "__main__":
    asyncio.run(main())

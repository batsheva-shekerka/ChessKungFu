"""Gateway listener for matchmaker Redis pub/sub events."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

from application.game_service import GameService
from application.ports import AppLogger
from application.room_service import RoomService
from domain.models import PlayerRole
from infrastructure.matchmaking.redis_queue import EVENTS_CHANNEL, RedisMatchmakingQueue
from protocol import MatchFoundMessage, MatchTimeoutMessage, encode
from transport.connection_registry import ConnectionRegistry


async def run_matchmaker_event_listener(
    *,
    redis_url: str,
    rooms: RoomService,
    games: GameService,
    registry: ConnectionRegistry,
    logger: AppLogger,
    stop_event: asyncio.Event | None = None,
) -> None:
    queue = RedisMatchmakingQueue(redis_url)
    pubsub = queue.pubsub()
    pubsub.subscribe(EVENTS_CHANNEL)
    logger.info("Gateway listening for matchmaker events", channel=EVENTS_CHANNEL)

    try:
        while True:
            if stop_event is not None and stop_event.is_set():
                break
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
                logger.warning("Invalid matchmaker event JSON", raw=raw)
                continue
            await _handle_event(
                payload,
                rooms=rooms,
                games=games,
                registry=registry,
                logger=logger,
            )
    finally:
        try:
            pubsub.unsubscribe(EVENTS_CHANNEL)
            pubsub.close()
        except Exception:
            pass


async def _handle_event(
    payload: dict[str, Any],
    *,
    rooms: RoomService,
    games: GameService,
    registry: ConnectionRegistry,
    logger: AppLogger,
) -> None:
    event_type = payload.get("type")
    if event_type == "create_match":
        room_id = str(payload.get("room_id", ""))
        white_id = str(payload.get("white_id", ""))
        black_id = str(payload.get("black_id", ""))
        if not room_id or not white_id or not black_id:
            logger.warning("create_match missing fields", payload=payload)
            return
        try:
            room = rooms.create_matched_room(
                white_id, black_id, room_id=room_id
            )
        except ValueError as exc:
            logger.error("Failed to create matched room", exc=exc, room_id=room_id)
            return

        players = {
            PlayerRole.WHITE.value: white_id,
            PlayerRole.BLACK.value: black_id,
        }
        await registry.send_to_user(
            white_id,
            encode(
                MatchFoundMessage(
                    room_id=room.room_id,
                    players=players,
                    color=PlayerRole.WHITE.value,
                ).to_dict()
            ),
        )
        await registry.send_to_user(
            black_id,
            encode(
                MatchFoundMessage(
                    room_id=room.room_id,
                    players=players,
                    color=PlayerRole.BLACK.value,
                ).to_dict()
            ),
        )
        if games.get_engine(room.room_id) is not None:
            state = encode(games.build_state_dict(room.room_id))
            await registry.send_to_user(white_id, state)
            await registry.send_to_user(black_id, state)
        return

    if event_type == "match_timeout":
        user_id = str(payload.get("user_id", ""))
        reason = str(payload.get("reason", "matchmaking timeout"))
        if not user_id:
            return
        await registry.send_to_user(
            user_id,
            encode(MatchTimeoutMessage(reason=reason).to_dict()),
        )

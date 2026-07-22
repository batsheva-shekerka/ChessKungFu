from __future__ import annotations

from enum import Enum


class EventType(str, Enum):
    PLAYER_MOVE = "player_move"
    GAME_OVER = "game_over"
    SCORE_UPDATE = "score_update"
    ROOM_CREATED = "room_created"
    MATCH_FOUND = "match_found"
    PLAYER_DISCONNECTED = "player_disconnected"
    PLAYER_RECONNECTED = "player_reconnected"


# Backward-compatible aliases
PLAYER_MOVE = EventType.PLAYER_MOVE.value
GAME_OVER = EventType.GAME_OVER.value
SCORE_UPDATE = EventType.SCORE_UPDATE.value
ROOM_CREATED = EventType.ROOM_CREATED.value
MATCH_FOUND = EventType.MATCH_FOUND.value
PLAYER_DISCONNECTED = EventType.PLAYER_DISCONNECTED.value
PLAYER_RECONNECTED = EventType.PLAYER_RECONNECTED.value

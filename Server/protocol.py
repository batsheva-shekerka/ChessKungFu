"""
פרוטוקול הודעות JSON בין Client ל-Server.
זהות המשתמש מגיעה מ-session על החיבור — לא מ-username ב-payloads (חוץ מ-login).
"""

from __future__ import annotations

import json
from typing import Any


MSG_MOVE = "move"
MSG_ACK = "ack"
MSG_ERROR = "error"
MSG_STATE = "state"
MSG_WELCOME = "welcome"
MSG_LOGIN = "login"
MSG_LOGIN_OK = "login_ok"
MSG_GAME_OVER = "game_over"
MSG_AUTH = "auth"
MSG_AUTH_OK = "auth_ok"
MSG_PLAY = "play"
MSG_CANCEL_PLAY = "cancel_play"
MSG_ROOM_CREATE = "room_create"
MSG_ROOM_JOIN = "room_join"
MSG_MATCH_FOUND = "match_found"
MSG_MATCH_TIMEOUT = "match_timeout"
MSG_DISCONNECT_COUNTDOWN = "disconnect_countdown"


class ProtocolError(ValueError):
    """הודעה לא תקינה לפי הפרוטוקול."""


def encode(message: dict[str, Any]) -> str:
    return json.dumps(message, ensure_ascii=False)


def decode(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"invalid JSON: {exc.msg}") from exc

    if not isinstance(data, dict):
        raise ProtocolError("message must be a JSON object")

    msg_type = data.get("type")
    if not isinstance(msg_type, str) or not msg_type:
        raise ProtocolError("missing or invalid 'type'")

    return data


def parse_position(value: Any, field_name: str) -> tuple[int, int]:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not all(isinstance(n, int) and not isinstance(n, bool) for n in value)
    ):
        raise ProtocolError(f"'{field_name}' must be [row, col] integers")
    return value[0], value[1]


def parse_move(data: dict[str, Any]) -> tuple[tuple[int, int], tuple[int, int]]:
    if data.get("type") != MSG_MOVE:
        raise ProtocolError(f"expected type '{MSG_MOVE}', got '{data.get('type')}'")
    start = parse_position(data.get("start"), "start")
    end = parse_position(data.get("end"), "end")
    return start, end


def make_move(start: tuple[int, int], end: tuple[int, int]) -> dict[str, Any]:
    return {
        "type": MSG_MOVE,
        "start": [start[0], start[1]],
        "end": [end[0], end[1]],
    }


def make_ack(
    start: tuple[int, int], end: tuple[int, int], accepted: bool = True
) -> dict[str, Any]:
    return {
        "type": MSG_ACK,
        "accepted": accepted,
        "start": [start[0], start[1]],
        "end": [end[0], end[1]],
    }


def make_error(reason: str) -> dict[str, Any]:
    return {"type": MSG_ERROR, "reason": reason}


def make_state(
    pieces: list,
    score: dict,
    game_over: bool = False,
    winner=None,
    room_id: str | None = None,
) -> dict[str, Any]:
    msg: dict[str, Any] = {
        "type": MSG_STATE,
        "pieces": pieces,
        "score": score,
        "game_over": game_over,
        "winner": winner,
    }
    if room_id is not None:
        msg["room_id"] = room_id
    return msg


def make_welcome(color: str, player_count: int) -> dict[str, Any]:
    return {
        "type": MSG_WELCOME,
        "color": color,
        "player_count": player_count,
    }


def make_login(username: str, password: str) -> dict[str, Any]:
    return {
        "type": MSG_LOGIN,
        "username": username,
        "password": password,
    }


def make_login_ok(
    username: str,
    elo: int,
    user_id: str,
    token: str,
) -> dict[str, Any]:
    return {
        "type": MSG_LOGIN_OK,
        "username": username,
        "elo": elo,
        "user_id": user_id,
        "token": token,
    }


def parse_login(data: dict[str, Any]) -> tuple[str, str]:
    if data.get("type") != MSG_LOGIN:
        raise ProtocolError(f"expected type '{MSG_LOGIN}', got '{data.get('type')}'")
    username = data.get("username")
    password = data.get("password")
    if not isinstance(username, str) or not username.strip():
        raise ProtocolError("'username' must be a non-empty string")
    if not isinstance(password, str) or not password:
        raise ProtocolError("'password' must be a non-empty string")
    return username.strip(), password


def make_auth(token: str) -> dict[str, Any]:
    return {"type": MSG_AUTH, "token": token}


def parse_auth(data: dict[str, Any]) -> str:
    if data.get("type") != MSG_AUTH:
        raise ProtocolError(f"expected type '{MSG_AUTH}', got '{data.get('type')}'")
    token = data.get("token")
    if not isinstance(token, str) or not token:
        raise ProtocolError("'token' must be a non-empty string")
    return token


def make_auth_ok(user_id: str, username: str, elo: int) -> dict[str, Any]:
    return {
        "type": MSG_AUTH_OK,
        "user_id": user_id,
        "username": username,
        "elo": elo,
    }


def make_play() -> dict[str, Any]:
    return {"type": MSG_PLAY}


def make_cancel_play() -> dict[str, Any]:
    return {"type": MSG_CANCEL_PLAY}


def make_room_create() -> dict[str, Any]:
    return {"type": MSG_ROOM_CREATE}


def make_room_join(room_id: str) -> dict[str, Any]:
    return {"type": MSG_ROOM_JOIN, "room_id": room_id}


def parse_room_join(data: dict[str, Any]) -> str:
    if data.get("type") != MSG_ROOM_JOIN:
        raise ProtocolError(f"expected type '{MSG_ROOM_JOIN}', got '{data.get('type')}'")
    room_id = data.get("room_id")
    if not isinstance(room_id, str) or not room_id.strip():
        raise ProtocolError("'room_id' must be a non-empty string")
    return room_id.strip()


def make_game_over(winner: str, ratings: dict) -> dict[str, Any]:
    return {
        "type": MSG_GAME_OVER,
        "winner": winner,
        "ratings": ratings,
    }


def make_disconnect_countdown(
    room_id: str, user_id: str, seconds_left: int
) -> dict[str, Any]:
    return {
        "type": MSG_DISCONNECT_COUNTDOWN,
        "room_id": room_id,
        "user_id": user_id,
        "seconds_left": seconds_left,
    }

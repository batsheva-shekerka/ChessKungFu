"""
פרוטוקול הודעות JSON בין Client ל-Server.
זהות המשתמש מגיעה מ-session על החיבור — לא מ-username ב-payloads (חוץ מ-login).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional, Protocol, runtime_checkable


class MessageType(str, Enum):
    MOVE = "move"
    ACK = "ack"
    ERROR = "error"
    STATE = "state"
    WELCOME = "welcome"
    LOGIN = "login"
    LOGIN_OK = "login_ok"
    GAME_OVER = "game_over"
    AUTH = "auth"
    AUTH_OK = "auth_ok"
    PLAY = "play"
    CANCEL_PLAY = "cancel_play"
    ROOM_CREATE = "room_create"
    ROOM_JOIN = "room_join"
    MATCH_FOUND = "match_found"
    MATCH_TIMEOUT = "match_timeout"
    DISCONNECT_COUNTDOWN = "disconnect_countdown"
    REJOINED_ROOM = "rejoined_room"
    PLAY_QUEUED = "play_queued"
    PLAY_CANCELLED = "play_cancelled"
    ROOM_CREATED = "room_created"
    ROOM_JOINED = "room_joined"
    ROOM_UPDATE = "room_update"


# Backward-compatible aliases
MSG_MOVE = MessageType.MOVE.value
MSG_ACK = MessageType.ACK.value
MSG_ERROR = MessageType.ERROR.value
MSG_STATE = MessageType.STATE.value
MSG_WELCOME = MessageType.WELCOME.value
MSG_LOGIN = MessageType.LOGIN.value
MSG_LOGIN_OK = MessageType.LOGIN_OK.value
MSG_GAME_OVER = MessageType.GAME_OVER.value
MSG_AUTH = MessageType.AUTH.value
MSG_AUTH_OK = MessageType.AUTH_OK.value
MSG_PLAY = MessageType.PLAY.value
MSG_CANCEL_PLAY = MessageType.CANCEL_PLAY.value
MSG_ROOM_CREATE = MessageType.ROOM_CREATE.value
MSG_ROOM_JOIN = MessageType.ROOM_JOIN.value
MSG_MATCH_FOUND = MessageType.MATCH_FOUND.value
MSG_MATCH_TIMEOUT = MessageType.MATCH_TIMEOUT.value
MSG_DISCONNECT_COUNTDOWN = MessageType.DISCONNECT_COUNTDOWN.value
MSG_REJOINED_ROOM = MessageType.REJOINED_ROOM.value
MSG_PLAY_QUEUED = MessageType.PLAY_QUEUED.value
MSG_PLAY_CANCELLED = MessageType.PLAY_CANCELLED.value
MSG_ROOM_CREATED = MessageType.ROOM_CREATED.value
MSG_ROOM_JOINED = MessageType.ROOM_JOINED.value
MSG_ROOM_UPDATE = MessageType.ROOM_UPDATE.value


class ProtocolError(ValueError):
    """הודעה לא תקינה לפי הפרוטוקול."""


@runtime_checkable
class WireMessage(Protocol):
    def to_dict(self) -> dict[str, Any]: ...


def encode(message: dict[str, Any] | WireMessage) -> str:
    data = message.to_dict() if isinstance(message, WireMessage) else message
    return json.dumps(data, ensure_ascii=False)


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


@dataclass
class MoveMessage:
    start: tuple[int, int]
    end: tuple[int, int]
    type: str = field(default=MessageType.MOVE.value, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "start": [self.start[0], self.start[1]],
            "end": [self.end[0], self.end[1]],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MoveMessage:
        if data.get("type") != MessageType.MOVE.value:
            raise ProtocolError(
                f"expected type '{MessageType.MOVE.value}', got '{data.get('type')}'"
            )
        return cls(
            start=parse_position(data.get("start"), "start"),
            end=parse_position(data.get("end"), "end"),
        )


@dataclass
class AckMessage:
    start: tuple[int, int]
    end: tuple[int, int]
    accepted: bool = True
    room_id: Optional[str] = None
    type: str = field(default=MessageType.ACK.value, init=False)

    def to_dict(self) -> dict[str, Any]:
        msg: dict[str, Any] = {
            "type": self.type,
            "accepted": self.accepted,
            "start": [self.start[0], self.start[1]],
            "end": [self.end[0], self.end[1]],
        }
        if self.room_id is not None:
            msg["room_id"] = self.room_id
        return msg

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AckMessage:
        return cls(
            start=parse_position(data.get("start"), "start"),
            end=parse_position(data.get("end"), "end"),
            accepted=bool(data.get("accepted", True)),
            room_id=data.get("room_id"),
        )


@dataclass
class ErrorMessage:
    reason: str
    type: str = field(default=MessageType.ERROR.value, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "reason": self.reason}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ErrorMessage:
        return cls(reason=str(data.get("reason", "")))


@dataclass
class PieceSnapshot:
    row: int
    col: int
    color: str
    type: str
    status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PieceSnapshot:
        return cls(
            row=int(data["row"]),
            col=int(data["col"]),
            color=str(data["color"]),
            type=str(data["type"]),
            status=str(data["status"]),
        )


@dataclass
class StateMessage:
    pieces: list[PieceSnapshot]
    score: dict[str, Any]
    game_over: bool = False
    winner: Any = None
    room_id: Optional[str] = None
    type: str = field(default=MessageType.STATE.value, init=False)

    def to_dict(self) -> dict[str, Any]:
        msg: dict[str, Any] = {
            "type": self.type,
            "pieces": [p.to_dict() for p in self.pieces],
            "score": self.score,
            "game_over": self.game_over,
            "winner": self.winner,
        }
        if self.room_id is not None:
            msg["room_id"] = self.room_id
        return msg

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StateMessage:
        pieces_raw = data.get("pieces") or []
        pieces = [
            PieceSnapshot.from_dict(p) if isinstance(p, dict) else p
            for p in pieces_raw
        ]
        return cls(
            pieces=pieces,
            score=dict(data.get("score") or {}),
            game_over=bool(data.get("game_over", False)),
            winner=data.get("winner"),
            room_id=data.get("room_id"),
        )


@dataclass
class WelcomeMessage:
    color: str
    player_count: int
    type: str = field(default=MessageType.WELCOME.value, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "color": self.color,
            "player_count": self.player_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WelcomeMessage:
        return cls(
            color=str(data.get("color", "")),
            player_count=int(data.get("player_count", 0)),
        )


@dataclass
class LoginMessage:
    username: str
    password: str
    type: str = field(default=MessageType.LOGIN.value, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "username": self.username,
            "password": self.password,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LoginMessage:
        if data.get("type") != MessageType.LOGIN.value:
            raise ProtocolError(
                f"expected type '{MessageType.LOGIN.value}', got '{data.get('type')}'"
            )
        username = data.get("username")
        password = data.get("password")
        if not isinstance(username, str) or not username.strip():
            raise ProtocolError("'username' must be a non-empty string")
        if not isinstance(password, str) or not password:
            raise ProtocolError("'password' must be a non-empty string")
        return cls(username=username.strip(), password=password)


@dataclass
class LoginOkMessage:
    username: str
    elo: int
    user_id: str
    token: str
    type: str = field(default=MessageType.LOGIN_OK.value, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "username": self.username,
            "elo": self.elo,
            "user_id": self.user_id,
            "token": self.token,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LoginOkMessage:
        return cls(
            username=str(data.get("username", "")),
            elo=int(data.get("elo", 0)),
            user_id=str(data.get("user_id", "")),
            token=str(data.get("token", "")),
        )


@dataclass
class AuthMessage:
    token: str
    type: str = field(default=MessageType.AUTH.value, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "token": self.token}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuthMessage:
        if data.get("type") != MessageType.AUTH.value:
            raise ProtocolError(
                f"expected type '{MessageType.AUTH.value}', got '{data.get('type')}'"
            )
        token = data.get("token")
        if not isinstance(token, str) or not token:
            raise ProtocolError("'token' must be a non-empty string")
        return cls(token=token)


@dataclass
class AuthOkMessage:
    user_id: str
    username: str
    elo: int
    type: str = field(default=MessageType.AUTH_OK.value, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "user_id": self.user_id,
            "username": self.username,
            "elo": self.elo,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuthOkMessage:
        return cls(
            user_id=str(data.get("user_id", "")),
            username=str(data.get("username", "")),
            elo=int(data.get("elo", 0)),
        )


@dataclass
class PlayMessage:
    type: str = field(default=MessageType.PLAY.value, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlayMessage:
        return cls()


@dataclass
class CancelPlayMessage:
    type: str = field(default=MessageType.CANCEL_PLAY.value, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CancelPlayMessage:
        return cls()


@dataclass
class RoomCreateMessage:
    type: str = field(default=MessageType.ROOM_CREATE.value, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RoomCreateMessage:
        return cls()


@dataclass
class RoomJoinMessage:
    room_id: str
    type: str = field(default=MessageType.ROOM_JOIN.value, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "room_id": self.room_id}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RoomJoinMessage:
        if data.get("type") != MessageType.ROOM_JOIN.value:
            raise ProtocolError(
                f"expected type '{MessageType.ROOM_JOIN.value}', got '{data.get('type')}'"
            )
        room_id = data.get("room_id")
        if not isinstance(room_id, str) or not room_id.strip():
            raise ProtocolError("'room_id' must be a non-empty string")
        return cls(room_id=room_id.strip())


@dataclass
class GameOverMessage:
    winner: str
    ratings: dict[str, Any]
    room_id: Optional[str] = None
    type: str = field(default=MessageType.GAME_OVER.value, init=False)

    def to_dict(self) -> dict[str, Any]:
        msg: dict[str, Any] = {
            "type": self.type,
            "winner": self.winner,
            "ratings": self.ratings,
        }
        if self.room_id is not None:
            msg["room_id"] = self.room_id
        return msg

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameOverMessage:
        return cls(
            winner=str(data.get("winner", "")),
            ratings=dict(data.get("ratings") or {}),
            room_id=data.get("room_id"),
        )


@dataclass
class DisconnectCountdownMessage:
    room_id: str
    user_id: str
    seconds_left: int
    type: str = field(default=MessageType.DISCONNECT_COUNTDOWN.value, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "room_id": self.room_id,
            "user_id": self.user_id,
            "seconds_left": self.seconds_left,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DisconnectCountdownMessage:
        return cls(
            room_id=str(data.get("room_id", "")),
            user_id=str(data.get("user_id", "")),
            seconds_left=int(data.get("seconds_left", 0)),
        )


@dataclass
class RejoinedRoomMessage:
    room_id: str
    color: Optional[str]
    type: str = field(default=MessageType.REJOINED_ROOM.value, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "room_id": self.room_id,
            "color": self.color,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RejoinedRoomMessage:
        return cls(
            room_id=str(data.get("room_id", "")),
            color=data.get("color"),
        )


@dataclass
class PlayQueuedMessage:
    status: str
    type: str = field(default=MessageType.PLAY_QUEUED.value, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "status": self.status}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlayQueuedMessage:
        return cls(status=str(data.get("status", "")))


@dataclass
class PlayCancelledMessage:
    cancelled: bool
    type: str = field(default=MessageType.PLAY_CANCELLED.value, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "cancelled": self.cancelled}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlayCancelledMessage:
        return cls(cancelled=bool(data.get("cancelled", False)))


@dataclass
class RoomCreatedMessage:
    room_id: str
    color: str
    player_count: int
    type: str = field(default=MessageType.ROOM_CREATED.value, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "room_id": self.room_id,
            "color": self.color,
            "player_count": self.player_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RoomCreatedMessage:
        return cls(
            room_id=str(data.get("room_id", "")),
            color=str(data.get("color", "")),
            player_count=int(data.get("player_count", 0)),
        )


@dataclass
class RoomJoinedMessage:
    room_id: str
    role: str
    color: str
    player_count: int
    type: str = field(default=MessageType.ROOM_JOINED.value, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "room_id": self.room_id,
            "role": self.role,
            "color": self.color,
            "player_count": self.player_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RoomJoinedMessage:
        return cls(
            room_id=str(data.get("room_id", "")),
            role=str(data.get("role", "")),
            color=str(data.get("color", "")),
            player_count=int(data.get("player_count", 0)),
        )


@dataclass
class RoomUpdateMessage:
    room_id: str
    player_count: int
    joined: str
    role: str
    type: str = field(default=MessageType.ROOM_UPDATE.value, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "room_id": self.room_id,
            "player_count": self.player_count,
            "joined": self.joined,
            "role": self.role,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RoomUpdateMessage:
        return cls(
            room_id=str(data.get("room_id", "")),
            player_count=int(data.get("player_count", 0)),
            joined=str(data.get("joined", "")),
            role=str(data.get("role", "")),
        )


@dataclass
class MatchFoundMessage:
    room_id: str
    players: dict[str, str]
    color: Optional[str] = None
    type: str = field(default=MessageType.MATCH_FOUND.value, init=False)

    def to_dict(self) -> dict[str, Any]:
        msg: dict[str, Any] = {
            "type": self.type,
            "room_id": self.room_id,
            "players": self.players,
        }
        if self.color is not None:
            msg["color"] = self.color
        return msg

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MatchFoundMessage:
        return cls(
            room_id=str(data.get("room_id", "")),
            players=dict(data.get("players") or {}),
            color=data.get("color"),
        )


@dataclass
class MatchTimeoutMessage:
    reason: str
    type: str = field(default=MessageType.MATCH_TIMEOUT.value, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "reason": self.reason}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MatchTimeoutMessage:
        return cls(reason=str(data.get("reason", "")))


# --- Compatibility helpers (return dict via to_dict) ---


def parse_move(data: dict[str, Any]) -> tuple[tuple[int, int], tuple[int, int]]:
    msg = MoveMessage.from_dict(data)
    return msg.start, msg.end


def make_move(start: tuple[int, int], end: tuple[int, int]) -> dict[str, Any]:
    return MoveMessage(start=start, end=end).to_dict()


def make_ack(
    start: tuple[int, int], end: tuple[int, int], accepted: bool = True
) -> dict[str, Any]:
    return AckMessage(start=start, end=end, accepted=accepted).to_dict()


def make_error(reason: str) -> dict[str, Any]:
    return ErrorMessage(reason=reason).to_dict()


def make_state(
    pieces: list,
    score: dict,
    game_over: bool = False,
    winner=None,
    room_id: str | None = None,
) -> dict[str, Any]:
    snap = [
        PieceSnapshot.from_dict(p) if isinstance(p, dict) else p for p in pieces
    ]
    return StateMessage(
        pieces=snap,
        score=score,
        game_over=game_over,
        winner=winner,
        room_id=room_id,
    ).to_dict()


def make_welcome(color: str, player_count: int) -> dict[str, Any]:
    return WelcomeMessage(color=color, player_count=player_count).to_dict()


def make_login(username: str, password: str) -> dict[str, Any]:
    return LoginMessage(username=username, password=password).to_dict()


def make_login_ok(
    username: str,
    elo: int,
    user_id: str,
    token: str,
) -> dict[str, Any]:
    return LoginOkMessage(
        username=username, elo=elo, user_id=user_id, token=token
    ).to_dict()


def parse_login(data: dict[str, Any]) -> tuple[str, str]:
    msg = LoginMessage.from_dict(data)
    return msg.username, msg.password


def make_auth(token: str) -> dict[str, Any]:
    return AuthMessage(token=token).to_dict()


def parse_auth(data: dict[str, Any]) -> str:
    return AuthMessage.from_dict(data).token


def make_auth_ok(user_id: str, username: str, elo: int) -> dict[str, Any]:
    return AuthOkMessage(user_id=user_id, username=username, elo=elo).to_dict()


def make_play() -> dict[str, Any]:
    return PlayMessage().to_dict()


def make_cancel_play() -> dict[str, Any]:
    return CancelPlayMessage().to_dict()


def make_room_create() -> dict[str, Any]:
    return RoomCreateMessage().to_dict()


def make_room_join(room_id: str) -> dict[str, Any]:
    return RoomJoinMessage(room_id=room_id).to_dict()


def parse_room_join(data: dict[str, Any]) -> str:
    return RoomJoinMessage.from_dict(data).room_id


def make_game_over(
    winner: str, ratings: dict, room_id: str | None = None
) -> dict[str, Any]:
    return GameOverMessage(
        winner=winner, ratings=ratings, room_id=room_id
    ).to_dict()


def make_disconnect_countdown(
    room_id: str, user_id: str, seconds_left: int
) -> dict[str, Any]:
    return DisconnectCountdownMessage(
        room_id=room_id, user_id=user_id, seconds_left=seconds_left
    ).to_dict()

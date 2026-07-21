from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PlayerRole(str, Enum):
    WHITE = "w"
    BLACK = "b"
    VIEWER = "viewer"


class ConnectionStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


@dataclass
class User:
    user_id: str
    username: str
    elo: int


@dataclass
class Session:
    token: str
    user_id: str
    expires_at: float


@dataclass
class QueueEntry:
    user_id: str
    elo: int
    enqueued_at: float


@dataclass
class RoomMember:
    user_id: str
    role: PlayerRole
    status: ConnectionStatus = ConnectionStatus.CONNECTED
    disconnect_deadline: Optional[float] = None


@dataclass
class Room:
    room_id: str
    members: dict[str, RoomMember] = field(default_factory=dict)
    elo_updated: bool = False
    game_started: bool = False

    def player_ids(self) -> list[str]:
        return [
            uid
            for uid, m in self.members.items()
            if m.role in (PlayerRole.WHITE, PlayerRole.BLACK)
        ]

    def color_of(self, user_id: str) -> Optional[str]:
        member = self.members.get(user_id)
        if member is None:
            return None
        if member.role == PlayerRole.WHITE:
            return "w"
        if member.role == PlayerRole.BLACK:
            return "b"
        return None

    def opponent_of(self, user_id: str) -> Optional[str]:
        my_color = self.color_of(user_id)
        if my_color is None:
            return None
        want = "b" if my_color == "w" else "w"
        for uid in self.player_ids():
            if self.color_of(uid) == want:
                return uid
        return None

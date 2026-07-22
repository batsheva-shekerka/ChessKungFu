"""Application-layer result objects (not wire protocol)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SessionOutcome:
    ok: bool
    reason: str = ""
    user_id: Optional[str] = None
    username: Optional[str] = None
    elo: Optional[int] = None
    token: Optional[str] = None
    rejoin_room_id: Optional[str] = None
    rejoin_color: Optional[str] = None


@dataclass
class CommandOutcome:
    """payload / broadcast_payload are wire dicts produced via DTO.to_dict()."""

    ok: bool
    reason: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    broadcast_user_ids: list[str] = field(default_factory=list)
    broadcast_payload: Optional[dict[str, Any]] = None


@dataclass
class MoveOutcome:
    ok: bool
    reason: str = ""
    room_id: Optional[str] = None
    start: Optional[tuple[int, int]] = None
    end: Optional[tuple[int, int]] = None
    member_ids: list[str] = field(default_factory=list)

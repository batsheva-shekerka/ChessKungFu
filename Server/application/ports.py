"""
Application ports (interfaces).

Application depends on these Protocols; Infrastructure implements them.
Wiring injects concrete adapters at composition root.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol

from domain.models import Session, User


class AppLogger(Protocol):
    def info(self, message: str, **ctx: Any) -> None: ...

    def warning(self, message: str, **ctx: Any) -> None: ...

    def error(
        self,
        message: str,
        *,
        exc: Optional[BaseException] = None,
        **ctx: Any,
    ) -> None: ...


class UserStore(Protocol):
    def register_or_login(
        self, username: str, password: str
    ) -> tuple[bool, str, Optional[User]]: ...

    def get_by_id(self, user_id: str) -> Optional[User]: ...

    def get_by_username(self, username: str) -> Optional[User]: ...

    def set_elo(self, user_id: str, elo: int) -> None: ...


class SessionStore(Protocol):
    def create(
        self, token: str, user_id: str, ttl_seconds: int = ...
    ) -> Session: ...

    def get_valid(self, token: str) -> Optional[Session]: ...

    def delete(self, token: str) -> None: ...


class EventPublisher(Protocol):
    def subscribe(self, event_type: str, listener: Any) -> None: ...

    async def publish(self, event_type: str, **payload: Any) -> None: ...


class GameEnginePort(Protocol):
    """Chess rules / realtime clock for one room."""

    def try_player_move(
        self,
        color: str,
        start: tuple[int, int],
        end: tuple[int, int],
    ) -> tuple[bool, str]: ...

    def update_game_clock(self, ms: int) -> None: ...

    def has_active_motion(self) -> bool: ...

    def force_forfeit(self, winner_color: str) -> None: ...

    def snapshot_state(self, room_id: str) -> dict[str, Any]: ...

    @property
    def game_over(self) -> bool: ...

    @property
    def winner(self) -> Optional[str]: ...


class GameEngineFactory(Protocol):
    def create(self) -> GameEnginePort: ...

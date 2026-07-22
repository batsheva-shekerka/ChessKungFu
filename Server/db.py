"""
Compatibility shim — prefer infrastructure.db.user_repository.
"""

from __future__ import annotations

from domain.elo import calc_elo as _calc_elo
from infrastructure.db.user_repository import (
    START_ELO,
    UserRepository,
)

_repo: UserRepository | None = None


def _get_repo() -> UserRepository:
    global _repo
    if _repo is None:
        import os

        db_path = os.path.join(os.path.dirname(__file__), "users.db")
        _repo = UserRepository(db_path)
    return _repo


def init_db() -> None:
    _get_repo().init_db()


def register_or_login(username: str, password: str):
    ok, reason, user = _get_repo().register_or_login(username, password)
    if not ok or user is None:
        return False, reason, None
    return True, reason, user.elo


def get_elo(username: str):
    user = _get_repo().get_by_username(username)
    return user.elo if user else None


def set_elo(username: str, elo: int) -> None:
    user = _get_repo().get_by_username(username)
    if user:
        _get_repo().set_elo(user.user_id, elo)


def calc_elo(winner_elo: int, loser_elo: int, k: int = 32):
    return _calc_elo(winner_elo, loser_elo, k)

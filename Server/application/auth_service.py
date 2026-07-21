from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Optional

from domain.models import User
from infrastructure.db.session_repository import SessionRepository
from infrastructure.db.user_repository import UserRepository


@dataclass
class LoginResult:
    ok: bool
    reason: str
    user: Optional[User] = None
    token: Optional[str] = None


class AuthService:
    def __init__(
        self,
        users: UserRepository,
        sessions: SessionRepository,
    ):
        self._users = users
        self._sessions = sessions

    def login(self, username: str, password: str) -> LoginResult:
        ok, reason, user = self._users.register_or_login(username, password)
        if not ok or user is None:
            return LoginResult(ok=False, reason=reason)
        token = secrets.token_urlsafe(32)
        self._sessions.create(token, user.user_id)
        return LoginResult(ok=True, reason=reason, user=user, token=token)

    def authenticate(self, token: str) -> Optional[User]:
        session = self._sessions.get_valid(token)
        if session is None:
            return None
        return self._users.get_by_id(session.user_id)

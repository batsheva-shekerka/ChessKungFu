from __future__ import annotations

from application.auth_service import AuthService
from application.dto import SessionOutcome
from application.ports import AppLogger
from application.room_service import RoomService
from domain.models import PlayerRole


class SessionService:
    """Login / token auth + optional room rejoin (application orchestration)."""

    def __init__(
        self,
        auth: AuthService,
        rooms: RoomService,
        logger: AppLogger,
    ):
        self._auth = auth
        self._rooms = rooms
        self._logger = logger

    def login(self, username: str, password: str) -> SessionOutcome:
        result = self._auth.login(username, password)
        if not result.ok or result.user is None or result.token is None:
            return SessionOutcome(ok=False, reason=result.reason)
        return self._finalize(result.user.user_id, result.user.username, result.user.elo, result.token)

    def authenticate(self, token: str) -> SessionOutcome:
        user = self._auth.authenticate(token)
        if user is None:
            return SessionOutcome(ok=False, reason="invalid or expired token")
        return self._finalize(user.user_id, user.username, user.elo, token)

    def _finalize(
        self,
        user_id: str,
        username: str,
        elo: int,
        token: str,
    ) -> SessionOutcome:
        room_id = self._rooms.reconnect(user_id)
        rejoin_color = None
        if room_id:
            role = self._rooms.member_role(room_id, user_id)
            rejoin_color = (
                role.value
                if role and role != PlayerRole.VIEWER
                else PlayerRole.VIEWER.value
            )
            self._logger.info(
                "User re-authenticated into room",
                user_id=user_id,
                room_id=room_id,
            )
        else:
            self._logger.info("User logged in", user_id=user_id, username=username)

        return SessionOutcome(
            ok=True,
            user_id=user_id,
            username=username,
            elo=elo,
            token=token,
            rejoin_room_id=room_id,
            rejoin_color=rejoin_color,
        )

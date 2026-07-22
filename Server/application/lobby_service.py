from __future__ import annotations

from application.dto import CommandOutcome
from application.matchmaking_service import MatchmakingService
from application.ports import AppLogger
from application.room_service import RoomService
from domain.models import PlayerRole
from protocol import (
    PlayCancelledMessage,
    PlayQueuedMessage,
    RoomCreatedMessage,
    RoomJoinedMessage,
    RoomUpdateMessage,
)


class LobbyService:
    """Play queue + manual room create/join."""

    def __init__(
        self,
        rooms: RoomService,
        matchmaking: MatchmakingService,
        logger: AppLogger,
    ):
        self._rooms = rooms
        self._mm = matchmaking
        self._logger = logger

    def play(self, user_id: str) -> CommandOutcome:
        if self._rooms.room_id_for_user(user_id):
            return CommandOutcome(ok=False, reason="already in a room")
        status = self._mm.enqueue(user_id)
        return CommandOutcome(
            ok=True,
            payload=PlayQueuedMessage(status=status).to_dict(),
        )

    def cancel_play(self, user_id: str) -> CommandOutcome:
        cancelled = self._mm.cancel(user_id)
        return CommandOutcome(
            ok=True,
            payload=PlayCancelledMessage(cancelled=cancelled).to_dict(),
        )

    def create_room(self, user_id: str) -> CommandOutcome:
        try:
            room = self._rooms.create_room(user_id)
        except ValueError as exc:
            return CommandOutcome(ok=False, reason=str(exc))
        return CommandOutcome(
            ok=True,
            payload=RoomCreatedMessage(
                room_id=room.room_id,
                color=PlayerRole.WHITE.value,
                player_count=1,
            ).to_dict(),
        )

    def join_room(self, user_id: str, room_id: str) -> CommandOutcome:
        try:
            room, role = self._rooms.join_room(room_id, user_id)
        except ValueError as exc:
            return CommandOutcome(ok=False, reason=str(exc))

        players = len([
            m for m in room.members.values()
            if m.role in (PlayerRole.WHITE, PlayerRole.BLACK)
        ])
        color = (
            role.value
            if role != PlayerRole.VIEWER
            else PlayerRole.WHITE.value
        )
        return CommandOutcome(
            ok=True,
            payload=RoomJoinedMessage(
                room_id=room.room_id,
                role=role.value,
                color=color,
                player_count=players,
            ).to_dict(),
            broadcast_user_ids=list(room.members.keys()),
            broadcast_payload=RoomUpdateMessage(
                room_id=room.room_id,
                player_count=players,
                joined=user_id,
                role=role.value,
            ).to_dict(),
        )

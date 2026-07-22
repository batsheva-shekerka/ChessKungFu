from __future__ import annotations

import secrets
import time
from typing import Callable, Optional

from domain.models import ConnectionStatus, PlayerRole, Room, RoomMember
from application.ports import AppLogger


DISCONNECT_GRACE_SECONDS = 20


class RoomService:
    def __init__(
        self,
        logger: AppLogger,
        on_room_created: Callable[[str], None],
    ):
        self._rooms: dict[str, Room] = {}
        self._user_room: dict[str, str] = {}
        self._logger = logger
        self._on_room_created = on_room_created

    def get_room(self, room_id: str) -> Optional[Room]:
        return self._rooms.get(room_id)

    def room_id_for_user(self, user_id: str) -> Optional[str]:
        return self._user_room.get(user_id)

    def create_room(self, creator_user_id: str) -> Room:
        existing = self._user_room.get(creator_user_id)
        if existing:
            raise ValueError("already in a room")

        room_id = secrets.token_hex(3)
        room = Room(room_id=room_id)
        room.members[creator_user_id] = RoomMember(
            user_id=creator_user_id, role=PlayerRole.WHITE
        )
        self._rooms[room_id] = room
        self._user_room[creator_user_id] = room_id
        self._on_room_created(room_id)
        room.game_started = True
        self._logger.info("Room created", room_id=room_id, user_id=creator_user_id)
        return room

    def create_matched_room(self, user_a: str, user_b: str) -> Room:
        for uid in (user_a, user_b):
            if uid in self._user_room:
                raise ValueError(f"user already in room: {uid}")

        room_id = secrets.token_hex(3)
        room = Room(room_id=room_id)
        room.members[user_a] = RoomMember(user_id=user_a, role=PlayerRole.WHITE)
        room.members[user_b] = RoomMember(user_id=user_b, role=PlayerRole.BLACK)
        self._rooms[room_id] = room
        self._user_room[user_a] = room_id
        self._user_room[user_b] = room_id
        self._on_room_created(room_id)
        room.game_started = True
        self._logger.info("Matched room created", room_id=room_id, white=user_a, black=user_b)
        return room

    def join_room(self, room_id: str, user_id: str) -> tuple[Room, PlayerRole]:
        room = self._rooms.get(room_id)
        if room is None:
            raise ValueError("room not found")
        if user_id in self._user_room:
            raise ValueError("already in a room")

        players = [
            m for m in room.members.values()
            if m.role in (PlayerRole.WHITE, PlayerRole.BLACK)
        ]
        if len(players) == 0:
            role = PlayerRole.WHITE
        elif len(players) == 1:
            role = PlayerRole.BLACK
        else:
            role = PlayerRole.VIEWER

        room.members[user_id] = RoomMember(user_id=user_id, role=role)
        self._user_room[user_id] = room_id
        if role in (PlayerRole.WHITE, PlayerRole.BLACK) and not room.game_started:
            room.game_started = True
            self._on_room_created(room_id)
        self._logger.info("Joined room", room_id=room_id, user_id=user_id, role=role.value)
        return room, role

    def member_role(self, room_id: str, user_id: str) -> Optional[PlayerRole]:
        room = self._rooms.get(room_id)
        if room is None:
            return None
        member = room.members.get(user_id)
        return member.role if member else None

    def get_room_players(
        self, room_id: str
    ) -> tuple[Optional[str], Optional[str]]:
        room = self._rooms.get(room_id)
        if room is None:
            return None, None
        white = black = None
        for uid, m in room.members.items():
            if m.role == PlayerRole.WHITE:
                white = uid
            elif m.role == PlayerRole.BLACK:
                black = uid
        return white, black

    def mark_disconnected(self, user_id: str) -> Optional[str]:
        room_id = self._user_room.get(user_id)
        if room_id is None:
            return None
        room = self._rooms[room_id]
        member = room.members.get(user_id)
        if member is None or member.role == PlayerRole.VIEWER:
            self._user_room.pop(user_id, None)
            room.members.pop(user_id, None)
            return None
        member.status = ConnectionStatus.DISCONNECTED
        member.disconnect_deadline = time.time() + DISCONNECT_GRACE_SECONDS
        self._logger.info(
            "Player disconnected - grace started",
            room_id=room_id,
            user_id=user_id,
            grace=DISCONNECT_GRACE_SECONDS,
        )
        return room_id

    def reconnect(self, user_id: str) -> Optional[str]:
        room_id = self._user_room.get(user_id)
        if room_id is None:
            return None
        room = self._rooms.get(room_id)
        if room is None:
            return None
        member = room.members.get(user_id)
        if member is None:
            return None
        member.status = ConnectionStatus.CONNECTED
        member.disconnect_deadline = None
        self._logger.info("Player reconnected", room_id=room_id, user_id=user_id)
        return room_id

    def clear_disconnect_deadline(self, room_id: str, user_id: str) -> None:
        room = self._rooms.get(room_id)
        if room is None:
            return
        member = room.members.get(user_id)
        if member is None:
            return
        member.disconnect_deadline = None

    def expired_disconnects(self) -> list[tuple[str, str]]:
        """Returns list of (room_id, user_id) whose grace expired."""
        now = time.time()
        expired: list[tuple[str, str]] = []
        for room_id, room in self._rooms.items():
            for uid, member in room.members.items():
                if (
                    member.status == ConnectionStatus.DISCONNECTED
                    and member.disconnect_deadline is not None
                    and member.disconnect_deadline <= now
                    and member.role in (PlayerRole.WHITE, PlayerRole.BLACK)
                ):
                    expired.append((room_id, uid))
        return expired

    def disconnect_countdowns(self) -> list[tuple[str, str, int]]:
        """(room_id, user_id, seconds_left)"""
        now = time.time()
        result: list[tuple[str, str, int]] = []
        for room_id, room in self._rooms.items():
            for uid, member in room.members.items():
                if (
                    member.status == ConnectionStatus.DISCONNECTED
                    and member.disconnect_deadline is not None
                ):
                    left = max(0, int(member.disconnect_deadline - now))
                    result.append((room_id, uid, left))
        return result

    def is_elo_updated(self, room_id: str) -> bool:
        room = self._rooms.get(room_id)
        return bool(room and room.elo_updated)

    def mark_elo_updated(self, room_id: str) -> None:
        room = self._rooms.get(room_id)
        if room:
            room.elo_updated = True

"""Gateway-side room rejoin using Redis directory + game-server RPC."""

from __future__ import annotations

from typing import Optional

from domain.models import PlayerRole
from infrastructure.matchmaking.allocator import GameAllocator
from infrastructure.messaging.game_bus import GameCommandBus


class RedisRoomRejoinProxy:
    """
    Satisfies SessionService's rooms.reconnect / member_role needs
    without holding rooms in the thin gateway process.
    """

    def __init__(self, bus: GameCommandBus, allocator: GameAllocator, logger=None):
        self._bus = bus
        self._allocator = allocator
        self._logger = logger
        self._role_by_user: dict[str, tuple[str, PlayerRole]] = {}

    def reconnect(self, user_id: str) -> Optional[str]:
        room_id = self._allocator.room_for_user(user_id)
        if not room_id:
            return None
        shard = self._allocator.shard_for(room_id)
        if not shard:
            self._allocator.unbind_player(user_id)
            return None
        reply = self._bus.call(
            {"type": "player_reconnect", "user_id": user_id},
            timeout=3.0,
            shard_id=shard,
        )
        if not reply.get("ok"):
            # Stale Redis mapping (room already gone on shard).
            self._allocator.unbind_player(user_id)
            if self._logger is not None:
                self._logger.info(
                    "Reconnect failed; cleared stale mapping",
                    user_id=user_id,
                    room_id=room_id,
                    error=reply.get("error"),
                )
            return None
        joined_room = str(reply.get("room_id") or room_id)
        color = str(reply.get("color") or "")
        role = _color_to_role(color)
        self._role_by_user[user_id] = (joined_room, role)
        if self._logger is not None:
            self._logger.info(
                "User reconnected via game shard",
                user_id=user_id,
                room_id=joined_room,
                shard_id=shard,
                color=color,
            )
        return joined_room

    def member_role(self, room_id: str, user_id: str) -> Optional[PlayerRole]:
        cached = self._role_by_user.get(user_id)
        if cached and cached[0] == room_id:
            return cached[1]
        return None


def _color_to_role(color: str) -> PlayerRole:
    if color == PlayerRole.WHITE.value:
        return PlayerRole.WHITE
    if color == PlayerRole.BLACK.value:
        return PlayerRole.BLACK
    return PlayerRole.VIEWER

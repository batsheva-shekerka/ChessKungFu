"""Gateway-side proxies that forward lobby/game ops to the game-server via Redis."""

from __future__ import annotations

from typing import Any

from application.dto import CommandOutcome, MoveOutcome
from infrastructure.matchmaking.allocator import GameAllocator
from infrastructure.messaging.game_bus import GameCommandBus


class RemoteLobbyProxy:
    def __init__(
        self, bus: GameCommandBus, matchmaking, allocator: GameAllocator
    ):
        self._bus = bus
        self._mm = matchmaking
        self._allocator = allocator

    def play(self, user_id: str) -> CommandOutcome:
        status = self._mm.enqueue(user_id)
        from protocol import PlayQueuedMessage

        return CommandOutcome(
            ok=True, payload=PlayQueuedMessage(status=status).to_dict()
        )

    def cancel_play(self, user_id: str) -> CommandOutcome:
        cancelled = self._mm.cancel(user_id)
        from protocol import PlayCancelledMessage

        return CommandOutcome(
            ok=True, payload=PlayCancelledMessage(cancelled=cancelled).to_dict()
        )

    def create_room(self, user_id: str) -> CommandOutcome:
        shard = self._allocator.pick_shard()
        reply = self._bus.call(
            {"type": "room_create", "user_id": user_id},
            shard_id=shard,
        )
        return self._to_command_outcome(reply)

    def join_room(self, user_id: str, room_id: str) -> CommandOutcome:
        shard = self._allocator.shard_for(room_id)
        if not shard:
            return CommandOutcome(ok=False, reason="room not found on any shard")
        reply = self._bus.call(
            {"type": "room_join", "user_id": user_id, "room_id": room_id},
            shard_id=shard,
        )
        return self._to_command_outcome(reply)

    @staticmethod
    def _to_command_outcome(reply: dict[str, Any]) -> CommandOutcome:
        if not reply.get("ok"):
            return CommandOutcome(ok=False, reason=str(reply.get("error", "game error")))
        return CommandOutcome(
            ok=True,
            payload=reply.get("payload") or {},
            broadcast_user_ids=list(reply.get("broadcast_user_ids") or []),
            broadcast_payload=reply.get("broadcast_payload"),
            extra_payloads=list(reply.get("extra_payloads") or []),
        )


class RemoteGameProxy:
    def __init__(
        self,
        bus: GameCommandBus,
        allocator: GameAllocator,
        move_latency: Any | None = None,
    ):
        self._bus = bus
        self._allocator = allocator
        self._move_latency = move_latency

    async def submit_move(
        self, user_id: str, start: tuple[int, int], end: tuple[int, int]
    ) -> MoveOutcome:
        import asyncio
        import time

        shard = self._allocator.shard_for_user(user_id)
        if not shard:
            return MoveOutcome(ok=False, reason="not in a game on any shard")
        t0 = time.perf_counter()
        reply = await asyncio.to_thread(
            self._bus.call,
            {
                "type": "move",
                "user_id": user_id,
                "start": list(start),
                "end": list(end),
            },
            5.0,
            shard_id=shard,
        )
        if self._move_latency is not None:
            self._move_latency.record((time.perf_counter() - t0) * 1000.0)
        if not reply.get("ok"):
            return MoveOutcome(ok=False, reason=str(reply.get("error", "move failed")))
        return MoveOutcome(
            ok=True,
            room_id=reply.get("room_id"),
            start=tuple(reply["start"]) if reply.get("start") else None,
            end=tuple(reply["end"]) if reply.get("end") else None,
            member_ids=list(reply.get("member_ids") or []),
        )

    def get_engine(self, room_id: str):
        return None

    def build_state_dict(self, room_id: str) -> dict:
        shard = self._allocator.shard_for(room_id)
        if not shard:
            return {}
        reply = self._bus.call(
            {"type": "get_state", "room_id": room_id},
            shard_id=shard,
        )
        if reply.get("ok") and isinstance(reply.get("payload"), dict):
            return reply["payload"]
        return {}

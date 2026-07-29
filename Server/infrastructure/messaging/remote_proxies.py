"""Gateway-side proxies that forward lobby/game ops to the game-server via Redis."""

from __future__ import annotations

from typing import Any

from application.dto import CommandOutcome, MoveOutcome
from infrastructure.messaging.game_bus import GameCommandBus


class RemoteLobbyProxy:
    def __init__(self, bus: GameCommandBus, matchmaking):
        self._bus = bus
        self._mm = matchmaking

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
        reply = self._bus.call({"type": "room_create", "user_id": user_id})
        return self._to_command_outcome(reply)

    def join_room(self, user_id: str, room_id: str) -> CommandOutcome:
        reply = self._bus.call(
            {"type": "room_join", "user_id": user_id, "room_id": room_id}
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
    def __init__(self, bus: GameCommandBus):
        self._bus = bus

    async def submit_move(
        self, user_id: str, start: tuple[int, int], end: tuple[int, int]
    ) -> MoveOutcome:
        import asyncio

        reply = await asyncio.to_thread(
            self._bus.call,
            {
                "type": "move",
                "user_id": user_id,
                "start": list(start),
                "end": list(end),
            },
        )
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
        reply = self._bus.call({"type": "get_state", "room_id": room_id})
        if reply.get("ok") and isinstance(reply.get("payload"), dict):
            return reply["payload"]
        return {}

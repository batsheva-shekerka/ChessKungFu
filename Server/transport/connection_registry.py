from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ConnectionContext:
    websocket: Any
    user_id: Optional[str] = None
    username: Optional[str] = None
    elo: Optional[int] = None
    token: Optional[str] = None

    @property
    def authenticated(self) -> bool:
        return self.user_id is not None


class ConnectionRegistry:
    def __init__(self):
        self._by_ws: dict[Any, ConnectionContext] = {}
        self._by_user: dict[str, ConnectionContext] = {}

    def add(self, websocket: Any) -> ConnectionContext:
        ctx = ConnectionContext(websocket=websocket)
        self._by_ws[websocket] = ctx
        return ctx

    def get(self, websocket: Any) -> Optional[ConnectionContext]:
        return self._by_ws.get(websocket)

    def bind_user(self, ctx: ConnectionContext, user_id: str, username: str, elo: int, token: str) -> None:
        # Drop previous socket for same user
        old = self._by_user.get(user_id)
        if old is not None and old.websocket is not ctx.websocket:
            old.user_id = None
        ctx.user_id = user_id
        ctx.username = username
        ctx.elo = elo
        ctx.token = token
        self._by_user[user_id] = ctx

    def remove(self, websocket: Any) -> Optional[ConnectionContext]:
        ctx = self._by_ws.pop(websocket, None)
        if ctx and ctx.user_id and self._by_user.get(ctx.user_id) is ctx:
            self._by_user.pop(ctx.user_id, None)
        return ctx

    def get_by_user(self, user_id: str) -> Optional[ConnectionContext]:
        return self._by_user.get(user_id)

    async def send_to_user(self, user_id: str, message: str) -> None:
        ctx = self._by_user.get(user_id)
        if ctx is None:
            return
        try:
            await ctx.websocket.send(message)
        except Exception:
            pass

    async def broadcast_users(self, user_ids: list[str], message: str) -> None:
        for uid in user_ids:
            await self.send_to_user(uid, message)

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from typing import Any

Listener = Callable[..., Any]


class AsyncEventBus:
    """Pub/sub לא חוסם: publish משבץ משימות וחוזר מיד."""

    def __init__(self, on_listener_error: Callable[[str, BaseException], None] | None = None):
        self._listeners: dict[str, list[Listener]] = {}
        self._on_listener_error = on_listener_error

    def subscribe(self, event_type: str, listener: Listener) -> None:
        self._listeners.setdefault(event_type, []).append(listener)

    async def publish(self, event_type: str, **payload: Any) -> None:
        for listener in list(self._listeners.get(event_type, [])):
            asyncio.create_task(self._safe_run(event_type, listener, payload))

    async def _safe_run(
        self,
        event_type: str,
        listener: Listener,
        payload: dict[str, Any],
    ) -> None:
        try:
            result = listener(**payload)
            if inspect.isawaitable(result):
                await result  # type: ignore[misc]
        except BaseException as exc:
            if self._on_listener_error is not None:
                self._on_listener_error(event_type, exc)

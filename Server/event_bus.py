"""Backward-compatible EventBus re-export (async implementation). """

from infrastructure.async_event_bus import AsyncEventBus

EventBus = AsyncEventBus

__all__ = ["EventBus", "AsyncEventBus"]

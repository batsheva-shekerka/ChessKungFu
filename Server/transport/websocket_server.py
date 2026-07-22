from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Optional

import websockets

from protocol import encode, make_error
from transport.connection_registry import ConnectionRegistry

if TYPE_CHECKING:
    from transport.message_router import MessageRouter
    from application.ports import AppLogger

DisconnectHandler = Callable[[str], Awaitable[None]]


class WebSocketServerApp:
    """
    Thin transport: accept sockets, receive/send frames, delegate to MessageRouter.
    No game rules, matchmaking, or room lifecycle logic.
    """

    def __init__(
        self,
        host: str,
        port: int,
        registry: ConnectionRegistry,
        router: "MessageRouter",
        logger: "AppLogger",
        on_client_disconnected: Optional[DisconnectHandler] = None,
    ):
        self._host = host
        self._port = port
        self._registry = registry
        self._router = router
        self._logger = logger
        self._on_client_disconnected = on_client_disconnected

    async def handle_client(self, websocket):
        ctx = self._registry.add(websocket)
        self._logger.info("Client connected")
        try:
            async for raw in websocket:
                await self._router.handle_raw(ctx, raw)
        except websockets.exceptions.ConnectionClosed:
            self._logger.info("Client connection closed", user_id=ctx.user_id)
        except Exception as exc:
            self._logger.error("Connection error", exc=exc, user_id=ctx.user_id)
            try:
                await websocket.send(encode(make_error("connection error")))
            except Exception as send_exc:
                self._logger.warning(
                    "Failed to send connection error to client",
                    user_id=ctx.user_id,
                    error=str(send_exc),
                )
        finally:
            removed = self._registry.remove(websocket)
            if (
                removed
                and removed.user_id
                and self._on_client_disconnected is not None
            ):
                await self._on_client_disconnected(removed.user_id)

    async def run(self):
        async with websockets.serve(self.handle_client, self._host, self._port):
            self._logger.info(
                f"WebSocket server listening on ws://{self._host}:{self._port}"
            )
            await asyncio.Future()

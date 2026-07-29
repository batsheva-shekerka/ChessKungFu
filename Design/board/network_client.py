"""
Threaded WebSocket client for the OpenCV graphics UI.
Talks to the server with the same JSON protocol as Server/client.py.
"""

from __future__ import annotations

import asyncio
import os
import queue
import sys
import threading
import time
from typing import Any, Optional

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
SERVER_DIR = os.path.join(ROOT_DIR, "Server")

for path in (ROOT_DIR, SERVER_DIR, CURRENT_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

from protocol import (  # noqa: E402
    MessageType,
    ProtocolError,
    decode,
    encode,
    make_auth,
    make_cancel_play,
    make_login,
    make_move,
    make_play,
    make_room_create,
    make_room_join,
)


class NetworkClient:
    """Background WebSocket client; UI reads state / polls events."""

    def __init__(
        self,
        uri: str = "ws://localhost:8765",
        api_base: str = "http://localhost:18088",
    ):
        self.uri = uri
        self.api_base = api_base.rstrip("/")
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ws = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.events: queue.Queue = queue.Queue()

        self.connected = False
        self.logged_in = False
        self.username: Optional[str] = None
        self.user_id: Optional[str] = None
        self.elo: Optional[int] = None
        self.token: Optional[str] = None
        self.color: Optional[str] = None
        self.room_id: Optional[str] = None
        self.role: Optional[str] = None
        self.status = "Starting..."
        self.last_error: Optional[str] = None
        self.latest_state: Optional[dict[str, Any]] = None
        self.game_over_info: Optional[dict[str, Any]] = None
        self.in_game = False
        self.queued = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._thread_main, daemon=True)
        self._thread.start()
        for _ in range(100):
            if self._loop is not None:
                break
            time.sleep(0.02)

    def stop(self) -> None:
        self._stop.set()
        loop = self._loop
        ws = self._ws
        if loop and loop.is_running() and ws is not None:
            asyncio.run_coroutine_threadsafe(ws.close(), loop)
        if self._thread:
            self._thread.join(timeout=2.0)
        self.connected = False

    def poll_event(self) -> Optional[tuple[str, dict]]:
        try:
            return self.events.get_nowait()
        except queue.Empty:
            return None

    def login(self, username: str, password: str) -> None:
        """Login via HTTP API Gateway, then bind the WS session with the token."""

        def _http_login() -> None:
            import json
            import urllib.error
            import urllib.request

            url = f"{self.api_base}/api/login"
            payload = json.dumps(
                {"username": username, "password": password}
            ).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                try:
                    body = json.loads(exc.read().decode("utf-8"))
                    reason = body.get("error") or f"HTTP {exc.code}"
                except Exception:
                    reason = f"HTTP {exc.code}"
                self.last_error = str(reason)
                self.status = self.last_error
                self.events.put(("error", {"reason": self.last_error}))
                return
            except Exception as exc:
                # Fallback: WS login (monolith / old stack without api-gateway)
                self.status = f"API login failed ({exc}); trying WS login..."
                self._send(encode(make_login(username, password)))
                return

            if not data.get("ok"):
                self.last_error = str(data.get("error") or "login failed")
                self.status = self.last_error
                self.events.put(("error", {"reason": self.last_error}))
                return

            self._on_login_ok(data)
            token = data.get("token")
            if token:
                self._send(encode(make_auth(str(token))))

        threading.Thread(target=_http_login, daemon=True).start()

    def play(self) -> None:
        self._send(encode(make_play()))

    def cancel_play(self) -> None:
        self._send(encode(make_cancel_play()))

    def create_room(self) -> None:
        self._send(encode(make_room_create()))

    def join_room(self, room_id: str) -> None:
        self._send(encode(make_room_join(room_id)))

    def send_move(self, start: tuple[int, int], end: tuple[int, int]) -> None:
        self._send(encode(make_move(start, end)))

    def reset_game_session(self) -> None:
        with self._lock:
            self.color = None
            self.room_id = None
            self.role = None
            self.latest_state = None
            self.game_over_info = None
            self.in_game = False
            self.queued = False

    def _send(self, payload: str) -> None:
        loop = self._loop
        if loop is None or not loop.is_running() or self._ws is None:
            self.last_error = "Not connected to server"
            self.status = self.last_error
            self.events.put(("error", {"reason": self.last_error}))
            return
        asyncio.run_coroutine_threadsafe(self._ws.send(payload), loop)

    def _thread_main(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._amain())
        finally:
            try:
                self._loop.close()
            except Exception:
                pass
            self._loop = None

    async def _amain(self) -> None:
        try:
            import websockets
        except ImportError:
            self.status = "websockets package missing"
            self.last_error = self.status
            self.events.put(("error", {"reason": self.status}))
            return

        try:
            async with websockets.connect(self.uri) as websocket:
                self._ws = websocket
                self.connected = True
                self.status = "Connected — please log in"
                self.events.put(("connected", {}))
                try:
                    async for raw in websocket:
                        if self._stop.is_set():
                            break
                        self._handle_raw(raw)
                finally:
                    self._ws = None
                    self.connected = False
                    self.status = "Disconnected"
        except ConnectionRefusedError:
            self.status = "Could not connect — is the server running?"
            self.last_error = self.status
            self.events.put(("error", {"reason": self.status}))
        except Exception as exc:
            self.status = f"Connection error: {exc}"
            self.last_error = str(exc)
            self.events.put(("error", {"reason": self.status}))

    def _handle_raw(self, raw: str) -> None:
        try:
            data = decode(raw)
        except ProtocolError as exc:
            self.events.put(("error", {"reason": f"Bad message: {exc}"}))
            return

        msg_type = data.get("type")
        handler = {
            MessageType.LOGIN_OK.value: self._on_login_ok,
            MessageType.AUTH_OK.value: self._on_auth_ok,
            MessageType.ROOM_CREATED.value: self._on_room_created,
            MessageType.ROOM_JOINED.value: self._on_room_joined,
            MessageType.REJOINED_ROOM.value: self._on_rejoined,
            MessageType.PLAY_QUEUED.value: self._on_play_queued,
            MessageType.PLAY_CANCELLED.value: self._on_play_cancelled,
            MessageType.MATCH_FOUND.value: self._on_match_found,
            MessageType.MATCH_TIMEOUT.value: self._on_match_timeout,
            MessageType.DISCONNECT_COUNTDOWN.value: self._on_disconnect_countdown,
            MessageType.ACK.value: self._on_ack,
            MessageType.STATE.value: self._on_state,
            MessageType.GAME_OVER.value: self._on_game_over,
            MessageType.ERROR.value: self._on_error,
            MessageType.WELCOME.value: self._on_welcome,
            MessageType.ROOM_UPDATE.value: self._on_room_update,
        }.get(msg_type)

        if handler:
            handler(data)
        else:
            self.events.put(("message", data))

    def _on_login_ok(self, data: dict) -> None:
        self.logged_in = True
        self.token = data.get("token")
        self.user_id = data.get("user_id")
        self.username = data.get("username")
        self.elo = data.get("elo")
        self.status = f"Logged in as {self.username} (ELO {self.elo})"
        self.events.put(("login_ok", data))

    def _on_auth_ok(self, data: dict) -> None:
        self.logged_in = True
        self.username = data.get("username")
        self.user_id = data.get("user_id")
        self.elo = data.get("elo")
        self.status = f"Authenticated as {self.username}"
        self.events.put(("auth_ok", data))

    def _on_room_created(self, data: dict) -> None:
        self.room_id = data.get("room_id")
        self.color = data.get("color")
        self.role = data.get("color")
        self.in_game = True
        self.queued = False
        self.status = f"Room {self.room_id} created — you are {self.color}"
        self.events.put(("enter_game", data))

    def _on_room_joined(self, data: dict) -> None:
        self.room_id = data.get("room_id")
        self.color = data.get("color")
        self.role = data.get("role")
        self.in_game = True
        self.queued = False
        self.status = (
            f"Joined room {self.room_id} as {self.role} ({self.color})"
        )
        self.events.put(("enter_game", data))

    def _on_rejoined(self, data: dict) -> None:
        self.room_id = data.get("room_id")
        self.color = data.get("color")
        self.in_game = True
        self.status = f"Rejoined room {self.room_id} as {self.color}"
        self.events.put(("enter_game", data))

    def _on_play_queued(self, data: dict) -> None:
        self.queued = True
        self.status = "Looking for opponent..."
        self.events.put(("play_queued", data))

    def _on_play_cancelled(self, data: dict) -> None:
        self.queued = False
        self.status = "Left matchmaking queue"
        self.events.put(("play_cancelled", data))

    def _on_match_found(self, data: dict) -> None:
        self.room_id = data.get("room_id")
        self.color = data.get("color")
        self.role = data.get("color")
        self.in_game = True
        self.queued = False
        self.status = f"Match found! You are {self.color}"
        self.events.put(("enter_game", data))

    def _on_match_timeout(self, data: dict) -> None:
        self.queued = False
        self.status = f"Matchmaking timeout: {data.get('reason')}"
        self.events.put(("match_timeout", data))

    def _on_disconnect_countdown(self, data: dict) -> None:
        self.status = (
            f"Opponent disconnect: {data.get('seconds_left')}s left"
        )
        self.events.put(("disconnect_countdown", data))

    def _on_ack(self, data: dict) -> None:
        self.events.put(("ack", data))

    def _on_state(self, data: dict) -> None:
        with self._lock:
            self.latest_state = data
        self.events.put(("state", data))

    def _on_game_over(self, data: dict) -> None:
        self.game_over_info = data
        winner = data.get("winner")
        self.status = f"Game over — winner: {winner}"
        self.events.put(("game_over", data))

    def _on_error(self, data: dict) -> None:
        reason = data.get("reason", "unknown error")
        self.last_error = reason
        self.status = f"Error: {reason}"
        self.events.put(("error", data))

    def _on_welcome(self, data: dict) -> None:
        self.color = data.get("color")
        self.status = f"Welcome — you are {self.color}"
        self.events.put(("welcome", data))

    def _on_room_update(self, data: dict) -> None:
        self.status = (
            f"Room update: {data.get('player_count')} players "
            f"(joined {data.get('role')})"
        )
        self.events.put(("room_update", data))

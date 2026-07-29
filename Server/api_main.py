"""HTTP API Gateway — non-realtime: login, room lookup, game history."""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

SERVER_ROOT = os.path.dirname(os.path.abspath(__file__))
if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)

from application.auth_service import AuthService
from bootstrap.logging_setup import create_server_logger
from bootstrap.wiring import (
    _build_game_history_store,
    _build_session_store,
    _build_user_store,
)
from infrastructure.matchmaking.allocator import GameAllocator
from infrastructure.observability import check_postgres, check_redis


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _game_to_dict(g) -> dict[str, Any]:
    return {
        "room_id": g.room_id,
        "white_id": g.white_id,
        "black_id": g.black_id,
        "winner": g.winner,
        "white_elo_before": g.white_elo_before,
        "black_elo_before": g.black_elo_before,
        "white_elo_after": g.white_elo_after,
        "black_elo_after": g.black_elo_after,
        "ended_at": g.ended_at,
    }


def create_handler(auth: AuthService, history, allocator: GameAllocator | None, logger):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            return

        def _cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

        def _send(self, code: int, payload: dict[str, Any]) -> None:
            raw = _json_bytes(payload)
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self._cors()
            self.end_headers()
            self.wfile.write(raw)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            try:
                data = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return {}
            return data if isinstance(data, dict) else {}

        def _bearer_token(self) -> str | None:
            auth_h = self.headers.get("Authorization") or ""
            if auth_h.lower().startswith("bearer "):
                return auth_h[7:].strip() or None
            return None

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            qs = parse_qs(parsed.query)

            if path in ("/health", "health"):
                redis_url = os.environ.get("REDIS_URL", "").strip()
                database_url = os.environ.get("DATABASE_URL", "").strip()
                redis_ok = check_redis(redis_url)
                pg_ok = check_postgres(database_url)
                ok = bool(redis_ok.get("ok")) and bool(pg_ok.get("ok"))
                self._send(
                    200 if ok else 503,
                    {
                        "service": "api-gateway",
                        "ok": ok,
                        "checks": {"redis": redis_ok, "postgres": pg_ok},
                    },
                )
                return

            if path in ("/metrics", "metrics"):
                try:
                    count = history.count()
                except Exception:
                    count = -1
                self._send(
                    200,
                    {
                        "service": "api-gateway",
                        "ok": True,
                        "games_recorded": count,
                    },
                )
                return

            if path == "/api/me":
                token = self._bearer_token() or (qs.get("token") or [None])[0]
                if not token:
                    self._send(401, {"ok": False, "error": "missing token"})
                    return
                user = auth.authenticate(token)
                if user is None:
                    self._send(401, {"ok": False, "error": "invalid or expired token"})
                    return
                self._send(
                    200,
                    {
                        "ok": True,
                        "user_id": user.user_id,
                        "username": user.username,
                        "elo": user.elo,
                    },
                )
                return

            if path == "/api/history" or path == "/api/games":
                token = self._bearer_token() or (qs.get("token") or [None])[0]
                limit = 20
                try:
                    limit = int((qs.get("limit") or ["20"])[0])
                except ValueError:
                    limit = 20
                if token:
                    user = auth.authenticate(token)
                    if user is None:
                        self._send(401, {"ok": False, "error": "invalid or expired token"})
                        return
                    games = history.list_for_user(user.user_id, limit=limit)
                else:
                    games = history.list_recent(limit=limit)
                self._send(
                    200,
                    {"ok": True, "games": [_game_to_dict(g) for g in games]},
                )
                return

            if path.startswith("/api/rooms/"):
                room_id = path[len("/api/rooms/") :].strip()
                if not room_id:
                    self._send(400, {"ok": False, "error": "missing room_id"})
                    return
                shard = allocator.shard_for(room_id) if allocator else None
                self._send(
                    200,
                    {
                        "ok": True,
                        "room_id": room_id,
                        "shard_id": shard,
                        "active": bool(shard),
                    },
                )
                return

            self._send(404, {"ok": False, "error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            if path != "/api/login":
                self._send(404, {"ok": False, "error": "not found"})
                return
            body = self._read_json()
            username = str(body.get("username") or "").strip()
            password = str(body.get("password") or "")
            if not username or not password:
                self._send(400, {"ok": False, "error": "username and password required"})
                return
            result = auth.login(username, password)
            if not result.ok or result.user is None or result.token is None:
                self._send(401, {"ok": False, "error": result.reason or "login failed"})
                return
            logger.info(
                "HTTP login ok",
                user_id=result.user.user_id,
                username=result.user.username,
                reason=result.reason,
            )
            self._send(
                200,
                {
                    "ok": True,
                    "reason": result.reason,
                    "token": result.token,
                    "user_id": result.user.user_id,
                    "username": result.user.username,
                    "elo": result.user.elo,
                },
            )

    return Handler


def main() -> None:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("API_PORT", os.environ.get("PORT", "8088")))
    redis_url = os.environ.get("REDIS_URL", "").strip()

    logger = create_server_logger(SERVER_ROOT)
    db_path = os.path.join(SERVER_ROOT, "users.db")
    users = _build_user_store(db_path, logger)
    sessions = _build_session_store(db_path, logger)
    history = _build_game_history_store(db_path, logger)
    auth = AuthService(users=users, sessions=sessions)
    allocator = GameAllocator(redis_url, shard_ids=["game-server-1"]) if redis_url else None

    handler = create_handler(auth, history, allocator, logger)
    server = ThreadingHTTPServer((host, port), handler)
    logger.info("HTTP API Gateway listening", host=host, port=port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

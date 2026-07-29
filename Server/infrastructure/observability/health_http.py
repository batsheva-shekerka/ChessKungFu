"""Lightweight HTTP /health and /metrics (stdlib only)."""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import urlparse

import redis


class LatencyTracker:
    """Rolling window of latency samples (milliseconds)."""

    def __init__(self, maxlen: int = 200):
        self._samples: deque[float] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def record(self, elapsed_ms: float) -> None:
        with self._lock:
            self._samples.append(float(elapsed_ms))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            samples = list(self._samples)
        if not samples:
            return {"count": 0, "avg_ms": None, "p95_ms": None, "max_ms": None}
        samples_sorted = sorted(samples)
        n = len(samples_sorted)
        p95_idx = min(n - 1, max(0, int(n * 0.95) - 1))
        return {
            "count": n,
            "avg_ms": round(sum(samples_sorted) / n, 2),
            "p95_ms": round(samples_sorted[p95_idx], 2),
            "max_ms": round(samples_sorted[-1], 2),
        }


def check_redis(redis_url: str) -> dict[str, Any]:
    if not redis_url:
        return {"ok": False, "error": "REDIS_URL missing"}
    try:
        r = redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=1)
        r.ping()
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def check_postgres(database_url: str) -> dict[str, Any]:
    if not database_url:
        return {"ok": True, "skipped": True}
    try:
        import psycopg

        with psycopg.connect(database_url, connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


SnapshotFn = Callable[[], dict[str, Any]]


def start_observability_server(
    *,
    host: str,
    port: int,
    service: str,
    snapshot: SnapshotFn,
    logger=None,
) -> ThreadingHTTPServer:
    """Start a daemon HTTP server serving /health and /metrics."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:  # quiet
            return

        def _write(self, code: int, body: dict[str, Any]) -> None:
            raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path.rstrip("/") or "/"
            try:
                data = snapshot()
            except Exception as exc:
                self._write(
                    503,
                    {
                        "service": service,
                        "ok": False,
                        "error": f"snapshot failed: {exc}",
                    },
                )
                return

            if path in ("/health", "health"):
                ok = bool(data.get("ok", False))
                self._write(
                    200 if ok else 503,
                    {
                        "service": service,
                        "ok": ok,
                        "checks": data.get("checks", {}),
                    },
                )
                return

            if path in ("/metrics", "metrics"):
                self._write(200, {"service": service, **data})
                return

            self._write(404, {"ok": False, "error": "not found"})

    server = ThreadingHTTPServer((host, port), Handler)
    thread = threading.Thread(
        target=server.serve_forever,
        name=f"obs-{service}",
        daemon=True,
    )
    thread.start()
    if logger is not None:
        logger.info("Observability HTTP started", service=service, port=port)
    return server


def timed_ms(fn, *args, **kwargs):
    """Run callable and return (result, elapsed_ms)."""
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, (time.perf_counter() - t0) * 1000.0

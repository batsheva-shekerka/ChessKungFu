"""
Simple load / smoke test against the Compose stack (ws://localhost:8765).

Usage (from repo root, with docker compose up):
  py -3 Server/load_test.py
  py -3 Server/load_test.py --pairs 2 --host localhost --port 8765

What it does:
  - Registers/logs in 2*N users
  - Enqueues Play for each pair
  - Waits for match_found
  - Sends a few legal-ish moves
  - Prints success / timing summary
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid

SERVER_ROOT = os.path.dirname(os.path.abspath(__file__))
if SERVER_ROOT not in sys.path:
    sys.path.insert(0, SERVER_ROOT)

import websockets

from protocol import (
    MessageType,
    decode,
    encode,
    make_login,
    make_move,
    make_play,
)


async def _recv_until(ws, wanted: set[str], timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = max(0.1, deadline - time.monotonic())
        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        msg = decode(raw)
        if msg.get("type") in wanted:
            return msg
    raise TimeoutError(f"timeout waiting for {wanted}")


async def _run_player(
    uri: str,
    username: str,
    password: str,
    *,
    expect_match: bool,
    moves: list[tuple[tuple[int, int], tuple[int, int]]],
) -> dict:
    t0 = time.perf_counter()
    result = {
        "username": username,
        "ok": False,
        "login_ms": None,
        "match_ms": None,
        "moves_ok": 0,
        "error": None,
    }
    try:
        async with websockets.connect(uri) as ws:
            await ws.send(encode(make_login(username, password)))
            login = await _recv_until(
                ws, {MessageType.LOGIN_OK.value, MessageType.ERROR.value}, 10
            )
            result["login_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            if login.get("type") == MessageType.ERROR.value:
                result["error"] = login.get("message") or login.get("reason") or "login error"
                return result

            await ws.send(encode(make_play()))
            # play_queued then match_found (or timeout)
            await _recv_until(
                ws,
                {
                    MessageType.PLAY_QUEUED.value,
                    MessageType.MATCH_FOUND.value,
                    MessageType.ERROR.value,
                },
                10,
            )
            if expect_match:
                match = await _recv_until(
                    ws,
                    {
                        MessageType.MATCH_FOUND.value,
                        MessageType.MATCH_TIMEOUT.value,
                        MessageType.ERROR.value,
                    },
                    45,
                )
                result["match_ms"] = round((time.perf_counter() - t0) * 1000, 1)
                if match.get("type") != MessageType.MATCH_FOUND.value:
                    result["error"] = f"no match: {match.get('type')}"
                    return result

                # drain optional board state
                try:
                    while True:
                        raw = await asyncio.wait_for(ws.recv(), timeout=0.3)
                        decode(raw)
                except (asyncio.TimeoutError, TimeoutError):
                    pass

                for start, end in moves:
                    await ws.send(encode(make_move(start, end)))
                    try:
                        msg = await _recv_until(
                            ws,
                            {
                                MessageType.ACK.value,
                                MessageType.ERROR.value,
                                MessageType.STATE.value,
                            },
                            5,
                        )
                        if msg.get("type") == MessageType.ACK.value and msg.get(
                            "accepted", True
                        ):
                            result["moves_ok"] += 1
                    except Exception:
                        break

            result["ok"] = True
            return result
    except Exception as exc:
        result["error"] = str(exc)
        return result


async def main_async(args: argparse.Namespace) -> int:
    uri = f"ws://{args.host}:{args.port}"
    password = "loadtest"
    pairs = max(1, args.pairs)
    print(f"Load test -> {uri} | pairs={pairs}")

    tasks = []
    for i in range(pairs):
        suffix = uuid.uuid4().hex[:6]
        u1 = f"lt_a_{i}_{suffix}"
        u2 = f"lt_b_{i}_{suffix}"
        # white-ish opening push (may be rejected by rules; still counts connectivity)
        moves_a = [((6, 4), (4, 4))]
        moves_b = [((1, 4), (3, 4))]
        tasks.append(
            _run_player(uri, u1, password, expect_match=True, moves=moves_a)
        )
        tasks.append(
            _run_player(uri, u2, password, expect_match=True, moves=moves_b)
        )

    results = await asyncio.gather(*tasks)
    ok = sum(1 for r in results if r["ok"])
    matches = sum(1 for r in results if r.get("match_ms") is not None and r["ok"])
    move_ok = sum(r.get("moves_ok", 0) for r in results)
    print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    print(
        f"Summary: ok={ok}/{len(results)} matched_clients={matches} moves_acked={move_ok}"
    )
    return 0 if ok == len(results) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="KungFu Chess compose load smoke test")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--pairs", type=int, default=1, help="number of matched pairs")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()

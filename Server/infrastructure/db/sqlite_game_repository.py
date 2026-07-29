"""SQLite game history — local/dev cold path after game_over."""

from __future__ import annotations

import os
import sqlite3
import time

from domain.models import GameResult


class SqliteGameRepository:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self.init_db()

    def init_db(self) -> None:
        os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS games (
                    room_id TEXT PRIMARY KEY,
                    white_id TEXT NOT NULL,
                    black_id TEXT NOT NULL,
                    winner TEXT NOT NULL,
                    white_elo_before INTEGER NOT NULL,
                    black_elo_before INTEGER NOT NULL,
                    white_elo_after INTEGER NOT NULL,
                    black_elo_after INTEGER NOT NULL,
                    ended_at REAL NOT NULL
                )
                """
            )

    def record(self, result: GameResult) -> None:
        ended_at = result.ended_at if result.ended_at is not None else time.time()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO games (
                    room_id, white_id, black_id, winner,
                    white_elo_before, black_elo_before,
                    white_elo_after, black_elo_after, ended_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.room_id,
                    result.white_id,
                    result.black_id,
                    result.winner,
                    result.white_elo_before,
                    result.black_elo_before,
                    result.white_elo_after,
                    result.black_elo_after,
                    ended_at,
                ),
            )

    def count(self) -> int:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM games").fetchone()
        return int(row[0]) if row else 0

    def list_recent(self, limit: int = 20) -> list[GameResult]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT room_id, white_id, black_id, winner,
                       white_elo_before, black_elo_before,
                       white_elo_after, black_elo_after, ended_at
                FROM games
                ORDER BY ended_at DESC
                LIMIT ?
                """,
                (max(1, min(limit, 100)),),
            ).fetchall()
        return [
            GameResult(
                room_id=r[0],
                white_id=r[1],
                black_id=r[2],
                winner=r[3],
                white_elo_before=int(r[4]),
                black_elo_before=int(r[5]),
                white_elo_after=int(r[6]),
                black_elo_after=int(r[7]),
                ended_at=float(r[8]) if r[8] is not None else None,
            )
            for r in rows
        ]

    def list_for_user(self, user_id: str, limit: int = 20) -> list[GameResult]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT room_id, white_id, black_id, winner,
                       white_elo_before, black_elo_before,
                       white_elo_after, black_elo_after, ended_at
                FROM games
                WHERE white_id = ? OR black_id = ?
                ORDER BY ended_at DESC
                LIMIT ?
                """,
                (user_id, user_id, max(1, min(limit, 100))),
            ).fetchall()
        return [
            GameResult(
                room_id=r[0],
                white_id=r[1],
                black_id=r[2],
                winner=r[3],
                white_elo_before=int(r[4]),
                black_elo_before=int(r[5]),
                white_elo_after=int(r[6]),
                black_elo_after=int(r[7]),
                ended_at=float(r[8]) if r[8] is not None else None,
            )
            for r in rows
        ]

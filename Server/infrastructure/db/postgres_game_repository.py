"""PostgreSQL game history — cold path after game_over."""

from __future__ import annotations

import time

import psycopg

from domain.models import GameResult


class PostgresGameRepository:
    def __init__(self, database_url: str):
        self._database_url = database_url
        self.init_db()

    def _connect(self):
        return psycopg.connect(self._database_url)

    def init_db(self) -> None:
        with self._connect() as conn:
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
                    ended_at DOUBLE PRECISION NOT NULL
                )
                """
            )
            conn.commit()

    def record(self, result: GameResult) -> None:
        ended_at = result.ended_at if result.ended_at is not None else time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO games (
                    room_id, white_id, black_id, winner,
                    white_elo_before, black_elo_before,
                    white_elo_after, black_elo_after, ended_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (room_id) DO NOTHING
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
            conn.commit()

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM games").fetchone()
        return int(row[0]) if row else 0

    def list_recent(self, limit: int = 20) -> list[GameResult]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT room_id, white_id, black_id, winner,
                       white_elo_before, black_elo_before,
                       white_elo_after, black_elo_after, ended_at
                FROM games
                ORDER BY ended_at DESC
                LIMIT %s
                """,
                (max(1, min(limit, 100)),),
            ).fetchall()
        return [_row_to_result(r) for r in rows]

    def list_for_user(self, user_id: str, limit: int = 20) -> list[GameResult]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT room_id, white_id, black_id, winner,
                       white_elo_before, black_elo_before,
                       white_elo_after, black_elo_after, ended_at
                FROM games
                WHERE white_id = %s OR black_id = %s
                ORDER BY ended_at DESC
                LIMIT %s
                """,
                (user_id, user_id, max(1, min(limit, 100))),
            ).fetchall()
        return [_row_to_result(r) for r in rows]


def _row_to_result(row) -> GameResult:
    return GameResult(
        room_id=row[0],
        white_id=row[1],
        black_id=row[2],
        winner=row[3],
        white_elo_before=int(row[4]),
        black_elo_before=int(row[5]),
        white_elo_after=int(row[6]),
        black_elo_after=int(row[7]),
        ended_at=float(row[8]) if row[8] is not None else None,
    )

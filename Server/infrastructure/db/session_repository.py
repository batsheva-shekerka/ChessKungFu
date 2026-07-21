from __future__ import annotations

import sqlite3
import time
from typing import Optional

from domain.models import Session

DEFAULT_TTL_SECONDS = 60 * 60 * 24  # 24h


class SessionRepository:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self.init_db()

    def init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    expires_at REAL NOT NULL
                )
                """
            )

    def create(self, token: str, user_id: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> Session:
        expires_at = time.time() + ttl_seconds
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, user_id, expires_at),
            )
        return Session(token=token, user_id=user_id, expires_at=expires_at)

    def get_valid(self, token: str) -> Optional[Session]:
        now = time.time()
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT token, user_id, expires_at FROM sessions WHERE token = ?",
                (token,),
            ).fetchone()
        if row is None:
            return None
        session = Session(token=row[0], user_id=row[1], expires_at=row[2])
        if session.expires_at < now:
            self.delete(token)
            return None
        return session

    def delete(self, token: str) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))

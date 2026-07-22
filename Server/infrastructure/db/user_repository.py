from __future__ import annotations

import hashlib
import os
import sqlite3
import uuid
from typing import Optional

from domain.models import User

START_ELO = 1200


class UserRepository:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self.init_db()

    def init_db(self) -> None:
        os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    elo INTEGER NOT NULL
                )
                """
            )
            self._migrate_legacy_users(conn)

    def _migrate_legacy_users(self, conn: sqlite3.Connection) -> None:
        """תמיכה ב-DB ישן בלי user_id: מוסיפים עמודה וממלאים."""
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }
        if "user_id" not in cols and "username" in cols:
            rows = conn.execute(
                "SELECT username, password_hash, elo FROM users"
            ).fetchall()
            conn.execute("ALTER TABLE users RENAME TO users_legacy")
            conn.execute(
                """
                CREATE TABLE users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    elo INTEGER NOT NULL
                )
                """
            )
            for username, password_hash, elo in rows:
                conn.execute(
                    "INSERT INTO users (user_id, username, password_hash, elo) VALUES (?, ?, ?, ?)",
                    (str(uuid.uuid4()), username, password_hash, elo),
                )
            conn.execute("DROP TABLE users_legacy")

    @staticmethod
    def hash_password(password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    def register_or_login(
        self, username: str, password: str
    ) -> tuple[bool, str, Optional[User]]:
        password_hash = self.hash_password(password)
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT user_id, username, password_hash, elo FROM users WHERE username = ?",
                (username,),
            ).fetchone()

        if row is None:
            user_id = str(uuid.uuid4())
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    "INSERT INTO users (user_id, username, password_hash, elo) VALUES (?, ?, ?, ?)",
                    (user_id, username, password_hash, START_ELO),
                )
            return True, "registered", User(user_id, username, START_ELO)

        user_id, uname, stored_hash, elo = row
        if stored_hash != password_hash:
            return False, "wrong password", None
        return True, "logged_in", User(user_id, uname, elo)

    def get_by_id(self, user_id: str) -> Optional[User]:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT user_id, username, elo FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return User(row[0], row[1], row[2])

    def get_by_username(self, username: str) -> Optional[User]:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT user_id, username, elo FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        if row is None:
            return None
        return User(row[0], row[1], row[2])

    def set_elo(self, user_id: str, elo: int) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE users SET elo = ? WHERE user_id = ?",
                (elo, user_id),
            )

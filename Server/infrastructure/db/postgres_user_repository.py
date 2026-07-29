"""PostgreSQL-backed UserStore — permanent users / Elo."""

from __future__ import annotations

import hashlib
import uuid
from typing import Optional

import psycopg

from domain.models import User
from infrastructure.db.user_repository import START_ELO


class PostgresUserRepository:
    """Implements UserStore using PostgreSQL (DATABASE_URL)."""

    def __init__(self, database_url: str):
        self._database_url = database_url
        self.init_db()

    def _connect(self):
        return psycopg.connect(self._database_url)

    def init_db(self) -> None:
        with self._connect() as conn:
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
            conn.commit()

    @staticmethod
    def hash_password(password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    def register_or_login(
        self, username: str, password: str
    ) -> tuple[bool, str, Optional[User]]:
        password_hash = self.hash_password(password)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT user_id, username, password_hash, elo FROM users WHERE username = %s",
                (username,),
            ).fetchone()

            if row is None:
                user_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO users (user_id, username, password_hash, elo) VALUES (%s, %s, %s, %s)",
                    (user_id, username, password_hash, START_ELO),
                )
                conn.commit()
                return True, "registered", User(user_id, username, START_ELO)

            user_id, uname, stored_hash, elo = row
            if stored_hash != password_hash:
                return False, "wrong password", None
            return True, "logged_in", User(user_id, uname, elo)

    def get_by_id(self, user_id: str) -> Optional[User]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT user_id, username, elo FROM users WHERE user_id = %s",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return User(row[0], row[1], row[2])

    def get_by_username(self, username: str) -> Optional[User]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT user_id, username, elo FROM users WHERE username = %s",
                (username,),
            ).fetchone()
        if row is None:
            return None
        return User(row[0], row[1], row[2])

    def set_elo(self, user_id: str, elo: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET elo = %s WHERE user_id = %s",
                (elo, user_id),
            )
            conn.commit()

from __future__ import annotations

import json
import sqlite3
from typing import Any


class SQLiteSessionProvider:

    def __init__(
        self,
        database: str = "smartops-session.db",
    ) -> None:

        self.database = database

        self._initialize()

    def _connect(self):
        return sqlite3.connect(
            self.database
        )

    def _initialize(self) -> None:

        with self._connect() as conn:

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL
                )
                """
            )

            conn.commit()

    def create(
        self,
        session_id: str,
        data: dict[str, Any] | None = None,
    ) -> None:

        self.save(
            session_id,
            data or {},
        )

    def save(
        self,
        session_id: str,
        data: dict[str, Any],
    ) -> None:

        payload = json.dumps(
            data,
            ensure_ascii=False,
        )

        with self._connect() as conn:

            conn.execute(
                """
                INSERT INTO sessions (
                    session_id,
                    data
                )
                VALUES (?, ?)
                ON CONFLICT(session_id)
                DO UPDATE SET data=excluded.data
                """,
                (
                    session_id,
                    payload,
                ),
            )

            conn.commit()

    def get(
        self,
        session_id: str,
    ) -> dict[str, Any] | None:

        with self._connect() as conn:

            row = conn.execute(
                """
                SELECT data
                FROM sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()

        if row is None:
            return None

        return json.loads(row[0])

    def exists(
        self,
        session_id: str,
    ) -> bool:

        return self.get(
            session_id
        ) is not None

    def delete(
        self,
        session_id: str,
    ) -> bool:

        with self._connect() as conn:

            cursor = conn.execute(
                """
                DELETE FROM sessions
                WHERE session_id = ?
                """,
                (session_id,),
            )

            conn.commit()

            return cursor.rowcount > 0
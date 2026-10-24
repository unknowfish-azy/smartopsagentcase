from __future__ import annotations

import json
from typing import Any

try:
    import psycopg
except ImportError:
    psycopg = None


class PostgreSQLSessionProvider:
    """
    PostgreSQL Session Provider。

    需要：
        psycopg
    """

    def __init__(
        self,
        *,
        host: str,
        port: int = 5432,
        user: str,
        password: str,
        database: str,
    ) -> None:

        if psycopg is None:
            raise ImportError(
                "Please install psycopg[binary]"
            )

        self.config = {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "dbname": database,
        }

        self._initialize()

    def _connect(self):

        return psycopg.connect(
            **self.config
        )

    def _initialize(self):

        with self._connect() as conn:

            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS agent_sessions (
                        session_id TEXT PRIMARY KEY,
                        data JSONB NOT NULL
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

            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    INSERT INTO agent_sessions (
                        session_id,
                        data
                    )
                    VALUES (%s, %s::jsonb)
                    ON CONFLICT(session_id)
                    DO UPDATE SET
                        data = EXCLUDED.data
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

            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT data
                    FROM agent_sessions
                    WHERE session_id = %s
                    """,
                    (session_id,),
                )

                row = cursor.fetchone()

        if row is None:
            return None

        return row[0]

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

            with conn.cursor() as cursor:

                cursor.execute(
                    """
                    DELETE FROM agent_sessions
                    WHERE session_id = %s
                    """,
                    (session_id,),
                )

                affected = cursor.rowcount

            conn.commit()

        return affected > 0
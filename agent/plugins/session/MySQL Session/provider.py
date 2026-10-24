from __future__ import annotations

import json
from typing import Any

try:
    import mysql.connector
except ImportError:
    mysql = None


class MySQLSessionProvider:
    """
    MySQL Session Provider。

    需要安装：

    mysql-connector-python
    """

    def __init__(
        self,
        *,
        host: str,
        port: int = 3306,
        user: str,
        password: str,
        database: str,
    ) -> None:

        if mysql is None:
            raise ImportError(
                "Please install mysql-connector-python"
            )

        self.config = {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "database": database,
        }

        self._initialize()

    def _connect(self):

        return mysql.connector.connect(
            **self.config
        )

    def _initialize(self):

        conn = self._connect()

        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_sessions (
                session_id VARCHAR(255) PRIMARY KEY,
                data JSON NOT NULL
            )
            """
        )

        conn.commit()

        cursor.close()
        conn.close()

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

        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO agent_sessions (
                session_id,
                data
            )
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE
                data = VALUES(data)
            """,
            (
                session_id,
                json.dumps(data, ensure_ascii=False),
            ),
        )

        conn.commit()

        cursor.close()
        conn.close()

    def get(
        self,
        session_id: str,
    ) -> dict[str, Any] | None:

        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT data
            FROM agent_sessions
            WHERE session_id = %s
            """,
            (session_id,),
        )

        row = cursor.fetchone()

        cursor.close()
        conn.close()

        if row is None:
            return None

        if isinstance(row[0], str):
            return json.loads(row[0])

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

        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute(
            """
            DELETE FROM agent_sessions
            WHERE session_id = %s
            """,
            (session_id,),
        )

        affected = cursor.rowcount

        conn.commit()

        cursor.close()
        conn.close()

        return affected > 0
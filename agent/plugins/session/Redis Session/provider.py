from __future__ import annotations

import json
from typing import Any

try:
    import redis
except ImportError:
    redis = None


class RedisSessionProvider:
    """
    Redis Session Provider。

    需要：

        redis
    """

    def __init__(
        self,
        *,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
        prefix: str = "smartops:session:",
        ttl: int | None = None,
    ) -> None:

        if redis is None:
            raise ImportError(
                "Please install redis"
            )

        self.client = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=True,
        )

        self.prefix = prefix
        self.ttl = ttl

    def _key(
        self,
        session_id: str,
    ) -> str:

        return (
            f"{self.prefix}{session_id}"
        )

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

        key = self._key(
            session_id
        )

        payload = json.dumps(
            data,
            ensure_ascii=False,
        )

        if self.ttl:
            self.client.setex(
                key,
                self.ttl,
                payload,
            )
        else:
            self.client.set(
                key,
                payload,
            )

    def get(
        self,
        session_id: str,
    ) -> dict[str, Any] | None:

        value = self.client.get(
            self._key(
                session_id
            )
        )

        if value is None:
            return None

        return json.loads(value)

    def exists(
        self,
        session_id: str,
    ) -> bool:

        return bool(
            self.client.exists(
                self._key(
                    session_id
                )
            )
        )

    def delete(
        self,
        session_id: str,
    ) -> bool:

        return (
            self.client.delete(
                self._key(
                    session_id
                )
            )
            > 0
        )
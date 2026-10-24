from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class FileSessionProvider:
    """
    基于JSON文件的Session Provider。

    适用于：
    - 开发
    - Demo
    - 本地测试
    """

    def __init__(
        self,
        root: str | Path,
    ) -> None:
        self.root = Path(root)

        self.root.mkdir(
            parents=True,
            exist_ok=True,
        )

    def _path(
        self,
        session_id: str,
    ) -> Path:

        safe_id = (
            session_id
            .replace("/", "_")
            .replace("\\", "_")
            .replace("..", "_")
        )

        return self.root / f"{safe_id}.json"

    def create(
        self,
        session_id: str,
        data: dict[str, Any] | None = None,
    ) -> None:

        if self.exists(session_id):
            return

        self.save(
            session_id,
            data or {},
        )

    def save(
        self,
        session_id: str,
        data: dict[str, Any],
    ) -> None:

        path = self._path(session_id)

        path.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def get(
        self,
        session_id: str,
    ) -> dict[str, Any] | None:

        path = self._path(session_id)

        if not path.exists():
            return None

        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    def exists(
        self,
        session_id: str,
    ) -> bool:

        return self._path(
            session_id
        ).exists()

    def delete(
        self,
        session_id: str,
    ) -> bool:

        path = self._path(session_id)

        if not path.exists():
            return False

        path.unlink()

        return True
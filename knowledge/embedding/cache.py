"""向量缓存：把 chunk 文本的向量落盘，重启时直接复用。

用标准库 sqlite3 实现，不引入新依赖。key 为
``sha256(model_name + "\\n" + text)``，因此：

- 语料内容变化 → 自动失效重算；
- 换模型 → key 全部失效，不会串用不同模型的向量；
- 只缓存 doc 向量，query 每次现算（query 文本变化多、复用率低）。
"""

from __future__ import annotations

import hashlib
import sqlite3
from array import array
from pathlib import Path


def cache_key(model_name: str, text: str) -> str:
    payload = f"{model_name}\n{text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class SqliteVectorCache:
    """SQLite 向量缓存。

    跨线程：KnowledgeService 有 RLock + 后台线程可能共享 cache 连接。
    sqlite3 默认 check_same_thread=True，多线程调用同一连接会抛 ProgrammingError。
    本类设 check_same_thread=False（生产环境还应在连接池层做，这里开发/演示够用）。
    """
    def __init__(self, path: str | Path, model_name: str) -> None:
        self.path = Path(path)
        self.model_name = model_name
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # RAG-P1-01：check_same_thread=False 允许跨线程共享同一 SQLite 连接
        # （KnowledgeService 有 RLock，实际并发不高）
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS embeddings ("
            "key TEXT PRIMARY KEY, dim INTEGER NOT NULL, vector BLOB NOT NULL)"
        )
        self._conn.commit()

    def get_many(self, keys: list[str]) -> dict[str, list[float]]:
        found: dict[str, list[float]] = {}
        # 分批查询，避免一次拼接过长的 SQL。
        for start in range(0, len(keys), 500):
            batch = keys[start:start + 500]
            placeholders = ",".join("?" for _ in batch)
            rows = self._conn.execute(
                f"SELECT key, dim, vector FROM embeddings WHERE key IN ({placeholders})",
                batch,
            ).fetchall()
            for key, dim, blob in rows:
                vector = array("f")
                vector.frombytes(blob)
                if len(vector) == dim:
                    found[key] = vector.tolist()
        return found

    def put_many(self, items: list[tuple[str, list[float]]]) -> None:
        if not items:
            return
        rows = [
            (key, len(vector), array("f", vector).tobytes())
            for key, vector in items
        ]
        self._conn.executemany(
            "INSERT OR REPLACE INTO embeddings (key, dim, vector) VALUES (?, ?, ?)",
            rows,
        )
        self._conn.commit()

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0])

    def close(self) -> None:
        self._conn.close()


__all__ = ["SqliteVectorCache", "cache_key"]

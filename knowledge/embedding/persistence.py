"""RAG-P1-01 持久化层：Document/Chunk/Embedding manifest + scope/ACL 预留 + 重启恢复。

任务书第 148 行："先文档/chunk/embedding/scope/ACL/manifest 适配与重启恢复，
再根据规模与同工作负载收益评估 FAISS 或 Qdrant"。

当前 corpus 规模：16 docs / 299 chunks（移除 RH 后）。规模极小，持久化更多是
"结构准备"而非"性能必需"。先给 KnowledgeService 加 save() / load()，
sqlite3 + pickle 存 chunks（含 chunk_index / metadata 里的 scope/ACL 预留字段）。

表结构：
  chunks: chunk_id TEXT PK, chunk_blob BLOB（整个 DocumentChunk pickle）, source, version
  manifest: key TEXT PK, value BLOB（PersistenceManifest JSON）
"""
from __future__ import annotations

import hashlib
import json
import pickle
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .backend_status import PersistenceManifest


class PersistenceManager:
    """RAG-P1-01：KnowledgeService 持久化。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_tables()

    def _init_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                document_id TEXT,
                chunk_blob BLOB NOT NULL,
                source TEXT,
                version TEXT
            );
            CREATE TABLE IF NOT EXISTS manifest (
                key TEXT PRIMARY KEY,
                value BLOB NOT NULL
            );
        """)
        self._conn.commit()

    def save(self, chunks: list[Any], manifest: PersistenceManifest,
             vectors: list[list[float]] | None = None) -> None:
        """把 chunks + manifest 写入 SQLite。

        chunks 直接 pickle 存储（保留 DocumentChunk 完整字段，包括 chunk_index）。
        """
        self._conn.execute("DELETE FROM chunks")
        self._conn.execute("DELETE FROM manifest")

        rows = []
        for chunk in chunks:
            rows.append((
                getattr(chunk, "chunk_id", ""),
                getattr(chunk, "document_id", ""),
                pickle.dumps(chunk),
                getattr(chunk, "source", ""),
                getattr(chunk, "version", "latest"),
            ))
        self._conn.executemany(
            "INSERT OR REPLACE INTO chunks (chunk_id, document_id, chunk_blob, source, version) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )

        self._conn.execute(
            "INSERT OR REPLACE INTO manifest (key, value) VALUES (?, ?)",
            ("manifest", json.dumps(manifest.to_dict(), ensure_ascii=False).encode("utf-8")),
        )
        self._conn.commit()

    def load(self) -> tuple[list[Any], PersistenceManifest | None]:
        """返回 (chunks, manifest)。若无持久化数据 → ([], None)。"""
        cur = self._conn.execute(
            "SELECT chunk_blob FROM chunks ORDER BY chunk_id"
        )
        rows = cur.fetchall()
        chunks = [pickle.loads(r[0]) for r in rows]

        manifest_row = self._conn.execute(
            "SELECT value FROM manifest WHERE key = 'manifest'"
        ).fetchone()
        manifest: PersistenceManifest | None = None
        if manifest_row:
            try:
                d = json.loads(manifest_row[0].decode("utf-8"))
                manifest = PersistenceManifest.from_dict(d)
            except Exception:
                manifest = None

        return chunks, manifest

    def count(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) FROM chunks")
        return int(cur.fetchone()[0])

    def clear(self) -> None:
        self._conn.execute("DELETE FROM chunks")
        self._conn.execute("DELETE FROM manifest")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


def compute_corpus_sha(chunks: Iterable[Any]) -> str:
    """RAG-P1-01：所有 chunk 的 content 聚合成 SHA-256，用作 manifest 版本键。"""
    h = hashlib.sha256()
    for c in sorted(chunks, key=lambda x: (getattr(x, "source", ""), getattr(x, "chunk_id", ""))):
        h.update(getattr(c, "source", "").encode("utf-8"))
        h.update(b"\x00")
        h.update(getattr(c, "content", "").encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


__all__ = ["PersistenceManager", "PersistenceManifest", "compute_corpus_sha"]

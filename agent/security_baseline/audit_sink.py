"""安全基线审计接收器（append-only + 哈希链防篡改）。

设计要点：
* 每条事件携带 seq / prev_hash / hash，后一条链住前一条，
  任何中间行被删改都会在 verify_chain() 处断链暴露；
* JSONL 只以追加模式打开，写入即 flush + fsync，进程崩溃也不丢已确认事件；
* 事件类型受 baseline.yaml 的 audit_required_events 白名单约束，
  非白名单事件在引擎层直接丢弃，审计文件不被噪声淹没；
* InMemoryAuditSink 供单测与进程内临时挂载使用，契约与文件版一致。
"""

from __future__ import annotations

import abc
import hashlib
import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


@dataclass
class BaselineEvent:
    """一条基线审计事件。hash 字段不参与自身哈希计算。"""

    seq: int
    timestamp: str
    event_type: str
    layer: str
    decision: str
    reasons: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    request_id: str = ""
    user_id: str = ""
    tool_name: str = ""
    action: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    prev_hash: str = ""
    hash: str = ""

    def to_line(self) -> str:
        data = asdict(self)
        data["reasons"] = list(self.reasons)
        data["evidence"] = list(self.evidence)
        return _canonical(data)


class AuditSink(abc.ABC):
    """审计接收器抽象契约。"""

    @abc.abstractmethod
    def record(self, event: BaselineEvent) -> None: ...

    @abc.abstractmethod
    def events(self) -> list[BaselineEvent]: ...

    @staticmethod
    def compute_hash(prev_hash: str, payload: dict[str, Any]) -> str:
        body = dict(payload)
        body.pop("hash", None)
        return hashlib.sha256(
            (prev_hash + _canonical(body)).encode("utf-8")
        ).hexdigest()


class InMemoryAuditSink(AuditSink):
    """进程内审计接收器，线程安全，供测试与默认挂载使用。

    与文件版保持同一套 seq/prev_hash/hash 上链语义，
    替换实现时审计事件的字段契约不变。
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._events: list[BaselineEvent] = []
        self._prev_hash = ""

    def record(self, event: BaselineEvent) -> None:
        with self._lock:
            event.seq = len(self._events) + 1
            event.prev_hash = self._prev_hash
            payload = asdict(event)
            payload["reasons"] = list(event.reasons)
            payload["evidence"] = list(event.evidence)
            payload.pop("hash", None)
            digest = self.compute_hash(self._prev_hash, payload)
            event.hash = digest
            self._events.append(event)
            self._prev_hash = digest

    def events(self) -> list[BaselineEvent]:
        with self._lock:
            return list(self._events)

    def event_types(self) -> list[str]:
        return [e.event_type for e in self.events()]


class JsonlAuditSink(AuditSink):
    """追加写 JSONL 文件的哈希链审计接收器。

    文件已存在时自动接续链尾（重开进程不丢链）；
    链尾损坏（最后一行写了一半）会在构造时抛出，禁止带病续链。
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._seq = 0
        self._prev_hash = ""
        self._recover_chain_tail()

    def _recover_chain_tail(self) -> None:
        if not self._path.exists() or self._path.stat().st_size == 0:
            return
        with self._path.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"审计日志第 {line_no} 行损坏，拒绝续链: {self._path}"
                    ) from exc
                stored_hash = payload.get("hash", "")
                expected = self.compute_hash(payload.get("prev_hash", ""), payload)
                if stored_hash != expected:
                    raise ValueError(
                        f"审计日志第 {line_no} 行哈希校验失败，疑似被篡改: {self._path}"
                    )
                self._seq = max(self._seq, int(payload["seq"]))
                self._prev_hash = stored_hash

    def record(self, event: BaselineEvent) -> None:
        with self._lock:
            event.seq = self._seq + 1
            event.prev_hash = self._prev_hash
            payload = asdict(event)
            payload["reasons"] = list(event.reasons)
            payload["evidence"] = list(event.evidence)
            payload.pop("hash", None)
            event.seq = self._seq + 1
            digest = self.compute_hash(self._prev_hash, payload)
            event.hash = digest
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(event.to_line() + "\n")
                fh.flush()
                import os

                os.fsync(fh.fileno())
            self._seq += 1
            self._prev_hash = digest

    def events(self) -> list[BaselineEvent]:
        with self._lock:
            if not self._path.exists():
                return []
            decoded: list[BaselineEvent] = []
            with self._path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    payload = json.loads(line)
                    payload["reasons"] = tuple(payload.get("reasons", ()))
                    payload["evidence"] = tuple(payload.get("evidence", ()))
                    decoded.append(BaselineEvent(**payload))
            return decoded

    @classmethod
    def verify_chain(cls, path: str | Path) -> dict[str, Any]:
        """全量重算哈希链，返回校验报告。

        ok=False 时 first_bad_line 给出首个断链/篡改行号，
        供审计巡检直接定位。
        """
        path = Path(path)
        if not path.exists():
            return {"ok": False, "count": 0, "first_bad_line": None, "reason": "file_missing"}
        prev_hash = ""
        count = 0
        with path.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    return {"ok": False, "count": count, "first_bad_line": line_no,
                            "reason": "invalid_json"}
                stored = payload.get("hash", "")
                if stored != cls.compute_hash(prev_hash, payload):
                    return {"ok": False, "count": count, "first_bad_line": line_no,
                            "reason": "hash_mismatch"}
                if payload.get("seq") != count + 1:
                    return {"ok": False, "count": count, "first_bad_line": line_no,
                            "reason": "seq_gap"}
                prev_hash = stored
                count += 1
        return {"ok": True, "count": count, "first_bad_line": None, "reason": ""}


def build_event(
    event_type: str,
    layer: str,
    decision: str,
    *,
    reasons: tuple[str, ...] = (),
    evidence: tuple[str, ...] = (),
    request_id: str = "",
    user_id: str = "",
    tool_name: str = "",
    action: str = "",
    extra: dict[str, Any] | None = None,
) -> BaselineEvent:
    """构造未上链事件（seq/hash 由 sink.record 填充）。"""
    return BaselineEvent(
        seq=0,
        timestamp=_utcnow_iso(),
        event_type=event_type,
        layer=layer,
        decision=decision,
        reasons=tuple(reasons),
        evidence=tuple(evidence),
        request_id=request_id,
        user_id=user_id,
        tool_name=tool_name,
        action=action,
        extra=extra or {},
    )


__all__ = [
    "AuditSink",
    "InMemoryAuditSink",
    "JsonlAuditSink",
    "BaselineEvent",
    "build_event",
]

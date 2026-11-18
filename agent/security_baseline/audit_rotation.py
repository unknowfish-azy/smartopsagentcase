"""按大小轮转的哈希链审计接收器。

在 JsonlAuditSink 的行格式与 sha256 哈希链语义之上增加：
* 活动文件写满 max_bytes 后滚动为编号分段（baseline.001.jsonl ...），
  哈希链跨分段连续——新分段首事件的 prev_hash 咬住上一分段尾哈希，链永不重置；
* 侧车清单 baseline.manifest.json 记录每个分段的首尾 seq/哈希/大小，
  清单自身带 manifest_hash，分段被替换、删除、夹带未登记文件都会在恢复时 fail-closed；
* 清单仅在轮转/剪枝时重写（原子 tmp+replace+fsync），活动段链尾仍由
  JSONL 哈希链自证，进程崩溃后按活动文件扫描恢复，不丢已确认事件；
* max_segments 可选保留策略：剪枝动作写入清单 pruned 历史并附被剪文件尾哈希，
  默认 None = 永久保留，绝不静默删除审计文件。
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .audit_sink import AuditSink, BaselineEvent, _canonical, _utcnow_iso

_MANIFEST_VERSION = 1


class RotatingJsonlAuditSink(AuditSink):
    """按文件大小轮转的 append-only 审计接收器。"""

    def __init__(
        self,
        path: str | Path,
        *,
        max_bytes: int = 10 * 1024 * 1024,
        max_segments: int | None = None,
    ) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes 必须为正整数")
        if max_segments is not None and max_segments <= 0:
            raise ValueError("max_segments 为空或正整数")
        self._dir = Path(path).parent
        self._base = Path(path).name
        stem = Path(path).stem
        self._segment_prefix = f"{stem}."
        self._segment_suffix = Path(path).suffix
        self._manifest_path = self._dir / f"{stem}.manifest.json"
        self._max_bytes = int(max_bytes)
        self._max_segments = max_segments
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._segments: list[dict[str, Any]] = []
        self._pruned: list[dict[str, Any]] = []
        self._next_index = 1
        self._seq = 0
        self._prev_hash = ""
        self._active_first_seq = 1
        self._active_first_prev = ""
        self._recover()

    # ------------------------------------------------------------------
    # 路径与清单
    # ------------------------------------------------------------------

    def _segment_name(self, index: int) -> str:
        return f"{self._segment_prefix}{index:03d}{self._segment_suffix}"

    def _write_manifest(self) -> None:
        payload = {
            "version": _MANIFEST_VERSION,
            "base_name": self._base,
            "segments": self._segments,
            "pruned": self._pruned,
            "next_index": self._next_index,
        }
        payload["manifest_hash"] = hashlib.sha256(
            _canonical({k: v for k, v in payload.items()}).encode("utf-8")
        ).hexdigest()
        tmp = self._manifest_path.with_suffix(".manifest.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            fh.write(_canonical(payload))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self._manifest_path)
        self._fsync_dir()

    def _fsync_dir(self) -> None:
        # Windows 下目录 fsync 不支持，缺失能力不影响文件内容原子替换语义
        if os.name == "nt":
            return
        fd = os.open(self._dir, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    # ------------------------------------------------------------------
    # 启动恢复（fail-closed）
    # ------------------------------------------------------------------

    def _recover(self) -> None:
        active_path = self._dir / self._base
        if not self._manifest_path.exists():
            # 存在编号分段却无清单 = 轮转历史被销毁，fail-closed；
            # 仅活动文件、从未轮转 = 新接收器正常态，按创世链自证恢复。
            if self._any_segment_files():
                raise ValueError(
                    f"审计清单缺失但存在分段数据，拒绝无锚点恢复: {self._manifest_path}"
                )
            if active_path.exists() and active_path.stat().st_size > 0:
                tail_seq, tail_hash = self._verify_file_head(
                    active_path,
                    expected_first_seq=1,
                    expected_first_prev="",
                    expected_size=None,
                )
                self._seq, self._prev_hash = tail_seq, tail_hash
                self._active_first_seq, self._active_first_prev = 1, ""
            return

        manifest = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        stored = manifest.pop("manifest_hash", "")
        expected = hashlib.sha256(_canonical(manifest).encode("utf-8")).hexdigest()
        if stored != expected:
            raise ValueError("审计清单 manifest_hash 校验失败，清单疑似被篡改")
        if manifest.get("version") != _MANIFEST_VERSION or manifest.get("base_name") != self._base:
            raise ValueError("审计清单版本或基名不匹配，拒绝恢复")

        self._segments = list(manifest.get("segments", []))
        self._pruned = list(manifest.get("pruned", []))
        self._next_index = int(manifest.get("next_index", 1))
        self._assert_no_untracked_files()

        # 逐分段锚定校验：每段首事件必须咬住登记的 first_prev_hash；
        # 相邻分段的首尾 seq/哈希必须连续，防止清单伪造锚点。
        for index, seg in enumerate(self._segments):
            if index > 0:
                prev_seg = self._segments[index - 1]
                if int(seg["first_seq"]) != int(prev_seg["last_seq"]) + 1:
                    raise ValueError(
                        f"审计分段 {seg['file']} 与前段 seq 不连续"
                    )
                if seg["first_prev_hash"] != prev_seg["last_hash"]:
                    raise ValueError(
                        f"审计分段 {seg['file']} 跨段锚点与前段尾哈希不符"
                    )
            self._verify_file_head(
                self._dir / seg["file"],
                expected_first_seq=int(seg["first_seq"]),
                expected_first_prev=seg["first_prev_hash"],
                expected_size=int(seg["size_bytes"]),
            )

        if self._segments:
            head = self._segments[-1]
            self._seq = int(head["last_seq"])
            self._prev_hash = head["last_hash"]
        else:
            self._seq, self._prev_hash = 0, ""

        self._active_first_seq = self._seq + 1
        self._active_first_prev = self._prev_hash
        if active_path.exists() and active_path.stat().st_size > 0:
            tail_seq, tail_hash = self._verify_file_head(
                active_path,
                expected_first_seq=self._active_first_seq,
                expected_first_prev=self._active_first_prev,
                expected_size=None,
            )
            self._seq, self._prev_hash = tail_seq, tail_hash

    def _any_segment_files(self) -> bool:
        return any(self._is_segment_name(p.name) for p in self._dir.iterdir())

    def _is_segment_name(self, name: str) -> bool:
        return (
            name.startswith(self._segment_prefix)
            and name.endswith(self._segment_suffix)
            and name != self._base
        )

    def _assert_no_untracked_files(self) -> None:
        tracked = {seg["file"] for seg in self._segments}
        for path in self._dir.iterdir():
            if self._is_segment_name(path.name) and path.name not in tracked:
                raise ValueError(f"发现未登记的审计分段，疑似文件替换: {path.name}")

    def _verify_file_head(
        self,
        path: Path,
        *,
        expected_first_seq: int,
        expected_first_prev: str,
        expected_size: int | None,
    ) -> tuple[int, str]:
        """校验单个审计文件的完整哈希链与 seq 连续性，返回 (尾 seq, 尾 hash)。"""
        if not path.exists():
            raise ValueError(f"审计分段缺失: {path.name}")
        # 内容哈希链是最强证据先校验，尺寸登记作为二次复核，
        # 避免内容篡改被尺寸报错抢先掩盖真实攻击类型。
        prev_hash = expected_first_prev
        expect_seq = expected_first_seq
        last_hash = expected_first_prev
        with path.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path.name} 第 {line_no} 行 JSON 损坏") from exc
                if payload.get("prev_hash") != prev_hash:
                    raise ValueError(f"{path.name} 第 {line_no} 行跨链锚点断裂")
                stored = payload.get("hash", "")
                if stored != self.compute_hash(prev_hash, payload):
                    raise ValueError(f"{path.name} 第 {line_no} 行哈希校验失败")
                if int(payload.get("seq", -1)) != expect_seq:
                    raise ValueError(f"{path.name} 第 {line_no} 行 seq 不连续")
                prev_hash, last_hash = stored, stored
                expect_seq += 1
        if expected_size is not None and path.stat().st_size != expected_size:
            raise ValueError(f"审计分段大小与清单不符: {path.name}")
        return expect_seq - 1, last_hash

    # ------------------------------------------------------------------
    # 写入与轮转
    # ------------------------------------------------------------------

    def record(self, event: BaselineEvent) -> None:
        with self._lock:
            active_path = self._dir / self._base
            line = self._build_line(event)

            # 活动段非空且再写一行就超限时先轮转；单行超大则照写，避免空转死循环
            if (
                active_path.exists()
                and active_path.stat().st_size > 0
                and active_path.stat().st_size + len(line.encode("utf-8")) + 1 > self._max_bytes
            ):
                self._rotate(active_path)

            with active_path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            self._seq += 1
            self._prev_hash = event.hash

    def _build_line(self, event: BaselineEvent) -> str:
        event.seq = self._seq + 1
        event.prev_hash = self._prev_hash
        payload = asdict(event)
        payload["reasons"] = list(event.reasons)
        payload["evidence"] = list(event.evidence)
        payload.pop("hash", None)
        event.hash = self.compute_hash(self._prev_hash, payload)
        return event.to_line()

    def _rotate(self, active_path: Path) -> None:
        index = self._next_index
        segment_name = self._segment_name(index)
        segment_path = self._dir / segment_name
        os.replace(active_path, segment_path)
        self._fsync_dir()

        self._segments.append({
            "file": segment_name,
            "first_seq": self._active_first_seq,
            "last_seq": self._seq,
            "event_count": self._seq - self._active_first_seq + 1,
            "first_prev_hash": self._active_first_prev,
            "last_hash": self._prev_hash,
            "size_bytes": segment_path.stat().st_size,
            "rotated_at": _utcnow_iso(),
        })
        self._next_index += 1
        self._prune_if_needed()
        self._write_manifest()

        self._active_first_seq = self._seq + 1
        self._active_first_prev = self._prev_hash

    def _prune_if_needed(self) -> None:
        if self._max_segments is None:
            return
        while len(self._segments) > self._max_segments:
            oldest = self._segments.pop(0)
            victim = self._dir / oldest["file"]
            if victim.exists():
                victim.unlink()
            self._fsync_dir()
            self._pruned.append({
                "file": oldest["file"],
                "last_seq": oldest["last_seq"],
                "last_hash": oldest["last_hash"],
                "pruned_at": datetime.now(timezone.utc).isoformat(),
            })

    # ------------------------------------------------------------------
    # 读取与巡检
    # ------------------------------------------------------------------

    def events(self) -> list[BaselineEvent]:
        with self._lock:
            decoded: list[BaselineEvent] = []
            files = [self._dir / seg["file"] for seg in self._segments]
            files.append(self._dir / self._base)
            for path in files:
                if not path.exists():
                    continue
                with path.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        payload = json.loads(line)
                        payload["reasons"] = tuple(payload.get("reasons", ()))
                        payload["evidence"] = tuple(payload.get("evidence", ()))
                        decoded.append(BaselineEvent(**payload))
            return decoded

    @property
    def segment_count(self) -> int:
        with self._lock:
            return len(self._segments)

    def verify_all(self) -> dict[str, Any]:
        """非抛出式全量巡检：清单哈希 + 全分段/活动段跨链锚点 + seq 连续性。"""
        try:
            with self._lock:
                if not self._manifest_path.exists():
                    if self._any_segment_files():
                        return {"ok": False, "total_events": 0, "segments": 0,
                                "first_bad_file": self._manifest_path.name,
                                "reason": "manifest_missing_with_segments"}
                    active = self._dir / self._base
                    if not active.exists() or active.stat().st_size == 0:
                        return {"ok": True, "total_events": 0, "segments": 0,
                                "first_bad_file": None, "reason": ""}
                    # 从未轮转的正常态：活动文件按创世链独立成验
                    tail_seq, _ = self._verify_file_head(
                        active, expected_first_seq=1,
                        expected_first_prev="", expected_size=None,
                    )
                    return {"ok": True, "total_events": tail_seq, "segments": 0,
                            "first_bad_file": None, "reason": ""}
                # 复用恢复逻辑做一次完整重算；构造期已校验，这里覆盖运行期外的篡改
                manifest = json.loads(self._manifest_path.read_text(encoding="utf-8"))
                stored = manifest.pop("manifest_hash", "")
                if stored != hashlib.sha256(
                    _canonical(manifest).encode("utf-8")
                ).hexdigest():
                    return {"ok": False, "total_events": 0, "segments": 0,
                            "first_bad_file": self._manifest_path.name,
                            "reason": "manifest_hash_mismatch"}

                total = 0
                # 最早可用分段可能承接已剪枝分段：锚点以清单登记值为准，
                # 相邻分段之间再独立校验首尾连续，剪枝边界由 pruned 历史背书。
                prev_hash, expect_seq = "", 1
                for index, seg in enumerate(manifest.get("segments", [])):
                    if index == 0:
                        anchor_seq = int(seg["first_seq"])
                        anchor_prev = seg["first_prev_hash"]
                    else:
                        anchor_seq = expect_seq
                        anchor_prev = prev_hash
                    tail_seq, tail_hash = self._verify_file_head(
                        self._dir / seg["file"],
                        expected_first_seq=anchor_seq,
                        expected_first_prev=anchor_prev,
                        expected_size=int(seg["size_bytes"]),
                    )
                    total += int(seg["event_count"])
                    expect_seq, prev_hash = tail_seq + 1, tail_hash

                active = self._dir / self._base
                if active.exists() and active.stat().st_size > 0:
                    tail_seq, _ = self._verify_file_head(
                        active,
                        expected_first_seq=expect_seq,
                        expected_first_prev=prev_hash,
                        expected_size=None,
                    )
                    total += tail_seq - expect_seq + 1
                return {"ok": True, "total_events": total,
                        "segments": len(manifest.get("segments", [])),
                        "first_bad_file": None, "reason": ""}
        except ValueError as exc:
            return {"ok": False, "total_events": 0, "segments": self.segment_count,
                    "first_bad_file": None, "reason": str(exc)}


__all__ = ["RotatingJsonlAuditSink"]

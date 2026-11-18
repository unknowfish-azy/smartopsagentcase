"""轮转审计接收器测试：滚动切分、跨段哈希链、清单防替换、剪枝留痕。"""

from __future__ import annotations

import json

import pytest

from agent.security_baseline import RotatingJsonlAuditSink
from agent.security_baseline.audit_sink import build_event


def _events(n: int, *, prefix: str = "evt"):
    return [
        build_event(
            "baseline.blocked",
            layer="L2_OPERATIONS",
            decision="BLOCK",
            reasons=(f"{prefix}-{i}-" + "x" * 40,),
            request_id=f"req-{i}",
        )
        for i in range(1, n + 1)
    ]


def _write(sink, events):
    for event in events:
        sink.record(event)


@pytest.fixture
def audit_path(tmp_path):
    return tmp_path / "audit" / "baseline.jsonl"


# --------------------------------------------------------------------------
# 轮转与跨段链
# --------------------------------------------------------------------------


def test_rotation_splits_files_with_continuous_chain(audit_path):
    sink = RotatingJsonlAuditSink(audit_path, max_bytes=500)
    _write(sink, _events(10))

    assert sink.segment_count >= 2
    assert (audit_path.parent / "baseline.manifest.json").exists()
    assert (audit_path.parent / "baseline.001.jsonl").exists()

    events = sink.events()
    assert [e.seq for e in events] == list(range(1, 11))
    # 跨分段边界：后一条事件的 prev_hash 必须咬住前一条的 hash
    for prev, curr in zip(events, events[1:]):
        assert curr.prev_hash == prev.hash

    report = sink.verify_all()
    assert report["ok"] is True
    assert report["total_events"] == 10


def test_reopen_recovers_and_continues_chain(audit_path):
    sink = RotatingJsonlAuditSink(audit_path, max_bytes=400)
    _write(sink, _events(8))
    tail_hash = sink.events()[-1].hash

    # 模拟进程重启：清单锚定分段，活动文件扫描续链
    reopened = RotatingJsonlAuditSink(audit_path, max_bytes=400)
    _write(reopened, _events(4, prefix="reopen"))

    events = reopened.events()
    assert [e.seq for e in events] == list(range(1, 13))
    assert events[8].prev_hash == tail_hash
    assert reopened.verify_all()["ok"] is True


def test_events_are_ordered_across_segments(audit_path):
    sink = RotatingJsonlAuditSink(audit_path, max_bytes=350)
    _write(sink, _events(9))
    request_ids = [e.request_id for e in sink.events()]
    assert request_ids == [f"req-{i}" for i in range(1, 10)]


def test_oversized_single_line_does_not_loop(audit_path):
    sink = RotatingJsonlAuditSink(audit_path, max_bytes=10)
    huge = build_event(
        "baseline.blocked", layer="L2_OPERATIONS", decision="BLOCK",
        reasons=("y" * 2000,),
    )
    sink.record(huge)  # 单行超容量也必须落盘，不得触发空轮转死循环
    assert audit_path.exists() and audit_path.stat().st_size > 2000
    assert sink.verify_all()["ok"] is True


# --------------------------------------------------------------------------
# fail-closed 恢复
# --------------------------------------------------------------------------


def test_tampered_segment_line_rejected(audit_path):
    sink = RotatingJsonlAuditSink(audit_path, max_bytes=400)
    _write(sink, _events(8))

    segment = audit_path.parent / "baseline.001.jsonl"
    lines = segment.read_text(encoding="utf-8").splitlines()
    payload = json.loads(lines[0])
    payload["reasons"] = ["FORGED"]
    lines[0] = json.dumps(payload, ensure_ascii=False)
    segment.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="哈希校验失败"):
        RotatingJsonlAuditSink(audit_path, max_bytes=400)


def test_deleted_segment_rejected(audit_path):
    sink = RotatingJsonlAuditSink(audit_path, max_bytes=400)
    _write(sink, _events(8))
    (audit_path.parent / "baseline.001.jsonl").unlink()

    with pytest.raises(ValueError, match="审计分段缺失"):
        RotatingJsonlAuditSink(audit_path, max_bytes=400)


def test_untracked_segment_rejected(audit_path):
    sink = RotatingJsonlAuditSink(audit_path, max_bytes=400)
    _write(sink, _events(8))
    # 夹带一个未在清单登记的分段文件，典型的审计文件替换攻击
    first = audit_path.parent / "baseline.001.jsonl"
    (audit_path.parent / "baseline.009.jsonl").write_text(
        first.read_text(encoding="utf-8"), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="未登记的审计分段"):
        RotatingJsonlAuditSink(audit_path, max_bytes=400)


def test_manifest_tamper_rejected(audit_path):
    sink = RotatingJsonlAuditSink(audit_path, max_bytes=400)
    _write(sink, _events(8))

    manifest = audit_path.parent / "baseline.manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["segments"][0]["last_seq"] = 999
    manifest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="manifest_hash 校验失败"):
        RotatingJsonlAuditSink(audit_path, max_bytes=400)


def test_missing_manifest_with_segments_fails_closed(audit_path):
    sink = RotatingJsonlAuditSink(audit_path, max_bytes=400)
    _write(sink, _events(8))  # 触发轮转，清单与编号分段都已落盘
    assert (audit_path.parent / "baseline.001.jsonl").exists()
    (audit_path.parent / "baseline.manifest.json").unlink()

    with pytest.raises(ValueError, match="审计清单缺失"):
        RotatingJsonlAuditSink(audit_path, max_bytes=400)


def test_pre_rotation_active_file_recovers_without_manifest(audit_path):
    # 从未轮转时只有活动文件、没有清单，属正常态，应按创世链恢复而非报错
    sink = RotatingJsonlAuditSink(audit_path, max_bytes=10_000)
    sink.record(build_event("baseline.blocked", layer="L2", decision="BLOCK"))
    assert not (audit_path.parent / "baseline.manifest.json").exists()

    reopened = RotatingJsonlAuditSink(audit_path, max_bytes=10_000)
    assert reopened.events()[0].seq == 1
    assert reopened.verify_all()["ok"] is True


def test_empty_directory_boots_without_manifest(audit_path):
    sink = RotatingJsonlAuditSink(audit_path, max_bytes=400)
    assert sink.events() == []
    assert sink.verify_all()["ok"] is True


# --------------------------------------------------------------------------
# 非抛出式巡检
# --------------------------------------------------------------------------


def test_verify_all_reports_runtime_tamper(audit_path):
    sink = RotatingJsonlAuditSink(audit_path, max_bytes=400)
    _write(sink, _events(8))

    segment = audit_path.parent / "baseline.001.jsonl"
    lines = segment.read_text(encoding="utf-8").splitlines()
    payload = json.loads(lines[0])
    payload["decision"] = "ALLOW"
    lines[0] = json.dumps(payload, ensure_ascii=False)
    segment.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = sink.verify_all()
    assert report["ok"] is False
    assert "哈希校验失败" in report["reason"]


# --------------------------------------------------------------------------
# 剪枝保留策略
# --------------------------------------------------------------------------


def test_pruning_keeps_limit_and_records_history(audit_path):
    sink = RotatingJsonlAuditSink(audit_path, max_bytes=350, max_segments=1)
    _write(sink, _events(15))

    assert sink.segment_count == 1
    manifest = json.loads(
        (audit_path.parent / "baseline.manifest.json").read_text(encoding="utf-8")
    )
    # 剪枝动作本身被清单留痕，且带被剪文件的尾哈希
    assert len(manifest["pruned"]) >= 1
    assert all("last_hash" in entry and "pruned_at" in entry
               for entry in manifest["pruned"])
    # 物理文件同步删除：只剩 1 个编号分段 + 1 个活动文件
    segment_files = [
        p for p in audit_path.parent.iterdir()
        if p.name.startswith("baseline.") and p.suffix == ".jsonl"
    ]
    assert len(segment_files) == 2
    assert any(p.name == "baseline.jsonl" for p in segment_files)
    # 剩余链自身仍然连续可验
    assert sink.verify_all()["ok"] is True
    seqs = [e.seq for e in sink.events()]
    assert seqs == list(range(seqs[0], seqs[-1] + 1))


def test_invalid_constructor_arguments(audit_path):
    with pytest.raises(ValueError):
        RotatingJsonlAuditSink(audit_path, max_bytes=0)
    with pytest.raises(ValueError):
        RotatingJsonlAuditSink(audit_path, max_bytes=100, max_segments=0)

"""哈希链审计接收器测试：追加写、断链检测、篡改暴露。"""

from __future__ import annotations

import json

import pytest

from agent.security_baseline import (
    BaselineEvent,
    InMemoryAuditSink,
    JsonlAuditSink,
)


def _event(event_type: str, reason: str) -> BaselineEvent:
    return BaselineEvent(
        seq=0,
        timestamp="2026-11-17T10:00:00+00:00",
        event_type=event_type,
        layer="L2_OPERATIONS",
        decision="BLOCK",
        reasons=(reason,),
    )


def test_in_memory_sink_records_in_order():
    sink = InMemoryAuditSink()
    sink.record(_event("baseline.blocked", "a"))
    sink.record(_event("baseline.redline_hit", "b"))
    events = sink.events()
    assert [e.seq for e in events] == [1, 2]
    assert events[0].prev_hash == ""
    assert events[1].prev_hash == events[0].hash
    assert sink.event_types() == ["baseline.blocked", "baseline.redline_hit"]


def test_jsonl_sink_appends_and_reopens_chain(tmp_path):
    path = tmp_path / "audit" / "baseline.jsonl"
    sink = JsonlAuditSink(path)
    sink.record(_event("baseline.compliance_hit", "CL-001"))
    sink.record(_event("baseline.redline_hit", "OL-001"))

    # 重开进程：从链尾接续，seq 与 prev_hash 不断链
    reopened = JsonlAuditSink(path)
    reopened.record(_event("quota.exhausted", "QUOTA"))

    report = JsonlAuditSink.verify_chain(path)
    assert report["ok"] is True
    assert report["count"] == 3
    assert [e.seq for e in reopened.events()] == [1, 2, 3]
    assert reopened.events()[2].prev_hash == reopened.events()[1].hash


def test_tampered_line_is_detected(tmp_path):
    path = tmp_path / "audit.jsonl"
    sink = JsonlAuditSink(path)
    for i in range(3):
        sink.record(_event("baseline.blocked", f"reason-{i}"))

    lines = path.read_text(encoding="utf-8").splitlines()
    payload = json.loads(lines[1])
    payload["reasons"] = ["FORGED_REASON"]
    lines[1] = json.dumps(payload, ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = JsonlAuditSink.verify_chain(path)
    assert report["ok"] is False
    assert report["first_bad_line"] == 2
    assert report["reason"] == "hash_mismatch"

    # 被篡改的文件禁止续链，避免坏链后面继续追加"合法"事件
    with pytest.raises(ValueError, match="哈希校验失败"):
        JsonlAuditSink(path)


def test_deleted_line_breaks_hash_chain(tmp_path):
    path = tmp_path / "audit.jsonl"
    sink = JsonlAuditSink(path)
    for i in range(3):
        sink.record(_event("baseline.blocked", f"reason-{i}"))

    lines = path.read_text(encoding="utf-8").splitlines()
    # 删除中间行：第 3 行的 prev_hash 立刻失去锚点，先表现为哈希不匹配
    path.write_text(lines[0] + "\n" + lines[2] + "\n", encoding="utf-8")

    report = JsonlAuditSink.verify_chain(path)
    assert report["ok"] is False
    assert report["first_bad_line"] == 2
    assert report["reason"] == "hash_mismatch"


def test_seq_gap_detected_even_with_valid_hashes(tmp_path):
    # 伪造一条哈希全部合法但 seq 从 1 跳到 3 的链，验证序号连续性独立校验
    path = tmp_path / "gap.jsonl"
    prev_hash = ""
    forged_lines = []
    for wanted_seq in (1, 3):
        payload = {
            "seq": wanted_seq,
            "timestamp": "2026-11-17T10:00:00+00:00",
            "event_type": "baseline.blocked",
            "layer": "L2_OPERATIONS",
            "decision": "BLOCK",
            "reasons": ["forged"],
            "evidence": [],
            "request_id": "",
            "user_id": "",
            "tool_name": "",
            "action": "",
            "extra": {},
            "prev_hash": prev_hash,
        }
        digest = JsonlAuditSink.compute_hash(prev_hash, payload)
        payload["hash"] = digest
        forged_lines.append(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        prev_hash = digest
    path.write_text("\n".join(forged_lines) + "\n", encoding="utf-8")

    report = JsonlAuditSink.verify_chain(path)
    assert report["ok"] is False
    assert report["reason"] == "seq_gap"
    assert report["first_bad_line"] == 2


def test_verify_missing_file(tmp_path):
    report = JsonlAuditSink.verify_chain(tmp_path / "nope.jsonl")
    assert report["ok"] is False
    assert report["reason"] == "file_missing"

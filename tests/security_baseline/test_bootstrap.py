"""安全基线装配工厂测试：组合根接线、哈希链续接、fail-closed 引导与端到端审计。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agent.security_baseline import (
    DEFAULT_AUDIT_DIR,
    DEFAULT_AUDIT_FILE_NAME,
    DEFAULT_MAX_BYTES,
    GateAction,
    RobotActionGuard,
    RotatingJsonlAuditSink,
    SecurityBaselineBundle,
    SecurityBaselineEngine,
    build_security_baseline,
)


def _emit(engine, request_id: str = "req-1", *, reason: str = "OL-001: 测试拦截"):
    return engine.emit_event(
        "baseline.blocked",
        layer="L2_OPERATIONS",
        decision="BLOCK",
        reasons=(reason,),
        request_id=request_id,
    )


# --------------------------------------------------------------------------
# 默认布局与组合包接线
# --------------------------------------------------------------------------


def test_default_audit_layout_constants():
    assert DEFAULT_AUDIT_DIR == Path("data/security_audit")
    assert DEFAULT_AUDIT_FILE_NAME == "baseline.jsonl"
    assert DEFAULT_MAX_BYTES == 10 * 1024 * 1024


def test_build_returns_fully_wired_bundle(tmp_path):
    bundle = build_security_baseline(audit_dir=tmp_path / "audit")

    assert isinstance(bundle, SecurityBaselineBundle)
    assert isinstance(bundle.engine, SecurityBaselineEngine)
    assert isinstance(bundle.audit_sink, RotatingJsonlAuditSink)
    assert isinstance(bundle.robot_guard, RobotActionGuard)
    # 引擎与接收器必须是同一个 sink 实例，接线在工厂内闭合
    assert bundle.engine.audit_sink is bundle.audit_sink
    assert bundle.audit_path == tmp_path / "audit" / "baseline.jsonl"
    assert (tmp_path / "audit").is_dir()
    # 首条事件写入前不创建活动文件，避免空文件污染哈希链恢复
    assert not bundle.audit_path.exists()


def test_robot_guard_can_be_skipped(tmp_path):
    bundle = build_security_baseline(
        audit_dir=tmp_path / "audit", with_robot_guard=False
    )
    assert bundle.robot_guard is None
    # 守卫缺省不影响引擎与审计链路
    assert _emit(bundle.engine) is not None
    assert bundle.verify_audit_chain()["ok"] is True


def test_bundle_is_frozen(tmp_path):
    bundle = build_security_baseline(audit_dir=tmp_path / "audit")
    with pytest.raises(AttributeError):
        bundle.engine = None  # type: ignore[misc]


# --------------------------------------------------------------------------
# 引擎 → 审计落盘的端到端链路
# --------------------------------------------------------------------------


def test_engine_emits_whitelisted_event_into_disk_chain(tmp_path):
    bundle = build_security_baseline(audit_dir=tmp_path / "audit")

    event = _emit(bundle.engine)
    assert event is not None
    assert bundle.audit_path.exists()

    events = bundle.audit_sink.events()
    assert len(events) == 1
    assert events[0].seq == 1
    assert events[0].prev_hash == ""
    assert events[0].event_type == "baseline.blocked"

    report = bundle.verify_audit_chain()
    assert report["ok"] is True
    assert report["total_events"] == 1


def test_non_whitelisted_event_is_dropped_silently(tmp_path):
    bundle = build_security_baseline(audit_dir=tmp_path / "audit")

    event = bundle.engine.emit_event("not.in.whitelist", layer="L2_OPERATIONS")
    assert event is None
    assert not bundle.audit_path.exists()


def test_robot_guard_connected_end_to_end(tmp_path):
    bundle = build_security_baseline(audit_dir=tmp_path / "audit")

    decision = bundle.robot_guard.screen_voice_command("cab-3", "立即拉闸")
    assert decision.allowed is False
    assert decision.action is GateAction.ESCALATE

    events = bundle.audit_sink.events()
    assert len(events) == 1
    assert events[0].event_type == "multimodal.escalation"
    assert events[0].tool_name == "robot.voice_command"
    assert bundle.verify_audit_chain()["ok"] is True


def test_rebuild_recovers_and_continues_chain(tmp_path):
    audit_dir = tmp_path / "audit"
    first = build_security_baseline(audit_dir=audit_dir)
    _emit(first.engine, request_id="req-1")
    _emit(first.engine, request_id="req-2")
    tail_hash = first.audit_sink.events()[-1].hash

    # 模拟进程重启：工厂再次装配时接收器做哈希链恢复并续编号
    reopened = build_security_baseline(audit_dir=audit_dir)
    _emit(reopened.engine, request_id="req-3")

    events = reopened.audit_sink.events()
    assert [e.seq for e in events] == [1, 2, 3]
    assert events[-1].prev_hash == tail_hash
    assert reopened.verify_audit_chain()["ok"] is True


# --------------------------------------------------------------------------
# fail-closed 引导：审计历史不可信时拒绝启动
# --------------------------------------------------------------------------


def test_tampered_history_fails_boot_fail_closed(tmp_path):
    audit_dir = tmp_path / "audit"
    bundle = build_security_baseline(audit_dir=audit_dir)
    _emit(bundle.engine)

    # 篡改活动行内容但不重算哈希，恢复校验必须识别并中断引导
    payload = json.loads(bundle.audit_path.read_text(encoding="utf-8").strip())
    payload["decision"] = "TAMPERED"
    bundle.audit_path.write_text(
        json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    with pytest.raises(ValueError):
        build_security_baseline(audit_dir=audit_dir)


def test_rotation_and_pruning_params_pass_through(tmp_path):
    bundle = build_security_baseline(
        audit_dir=tmp_path / "audit",
        max_bytes=300,
        max_segments=1,
    )
    for index in range(15):
        _emit(bundle.engine, request_id=f"req-{index}", reason="OL-001: " + "x" * 80)

    assert bundle.audit_sink.segment_count >= 1
    manifest_path = tmp_path / "audit" / "baseline.manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    # max_segments=1：超出分段被剪枝，但 pruned 历史必须留痕且带尾哈希
    assert manifest["pruned"]
    assert all("last_hash" in item for item in manifest["pruned"])
    assert bundle.verify_audit_chain()["ok"] is True


# --------------------------------------------------------------------------
# 参数校验与配置/时钟透传
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "",
        ".",
        "..",
        "../x.jsonl",
        "sub/x.jsonl",
        "notes.txt",
        "baseline.manifest.json",
    ],
)
def test_invalid_audit_file_names_rejected(tmp_path, name):
    with pytest.raises(ValueError):
        build_security_baseline(audit_dir=tmp_path / "audit", audit_file_name=name)


def test_invalid_rotation_params_propagate(tmp_path):
    with pytest.raises(ValueError):
        build_security_baseline(audit_dir=tmp_path / "audit", max_bytes=0)


def test_custom_config_path_is_wired(tmp_path):
    cfg = tmp_path / "custom-baseline.yaml"
    cfg.write_text(
        "version: 1\n"
        "L2_OPERATIONS:\n"
        "  redlines:\n"
        "    - id: OL-999\n"
        "      pattern: forbidden_token\n"
        "      message: factory custom rule\n"
        "      risk: HIGH\n",
        encoding="utf-8",
    )

    bundle = build_security_baseline(
        audit_dir=tmp_path / "audit", config_path=cfg
    )
    assert bundle.engine.config.source == str(cfg)

    decision = bundle.engine.evaluate_operation(
        tool_name="shell.exec", command="echo forbidden_token"
    )
    assert decision.allowed is False
    assert decision.reasons[0].startswith("OL-999")


def test_fixed_clock_is_accepted(tmp_path):
    fixed = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bundle = build_security_baseline(
        audit_dir=tmp_path / "audit", clock=lambda: fixed
    )
    # 时钟透传不影响装配与审计主链路；时钟语义本身由多模态测试矩阵覆盖
    assert _emit(bundle.engine) is not None
    assert bundle.verify_audit_chain()["ok"] is True

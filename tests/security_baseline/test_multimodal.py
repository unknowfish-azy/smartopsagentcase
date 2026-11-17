"""L3 多模态多源交叉验证测试。

场景全部来自真实对抗推演：对抗贴纸、温感伪造、阈值篡改、
自检告警屏蔽、单源误断电、同位置反复过热被自动抑制。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agent.security_baseline import (
    ArbitrationAction,
    CrossSourceValidator,
    ReadingVerdict,
    SensorReading,
    SensorType,
    load_baseline,
)


class FakeClock:
    def __init__(self, t: datetime) -> None:
        self.t = t

    def __call__(self) -> datetime:
        return self.t


@pytest.fixture
def now():
    return datetime(2026, 11, 17, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def validator(now):
    return CrossSourceValidator(load_baseline(), clock=FakeClock(now))


def _reading(source, stype, value, when, **kw):
    return SensorReading(
        source_id=source,
        sensor_type=stype,
        value=value,
        observed_at=when,
        location=kw.pop("location", "rack-03"),
        **kw,
    )


def test_single_vision_alarm_cannot_trigger_power_off(validator, now):
    readings = [_reading("cam-07", SensorType.VISION_FIRE, True, now)]
    result = validator.arbitrate(
        readings, scenario="fire_alarm", proposed_action="power.off"
    )
    assert result.action is ArbitrationAction.DESTRUCTIVE_BLOCKED
    assert result.allowed_destructive is False
    assert any("INSUFFICIENT_SOURCES" in r for r in result.reasons)


def test_two_distinct_sources_confirm_destructive(validator, now):
    readings = [
        _reading("thermal-03", SensorType.THERMAL, 80.0, now),
        _reading("cam-07", SensorType.VISION_FIRE, True, now),
    ]
    result = validator.arbitrate(
        readings, scenario="fire_alarm", proposed_action="power.off"
    )
    assert result.action is ArbitrationAction.DESTRUCTIVE_ALLOWED
    assert result.allowed_destructive is True
    assert set(result.agreeing_sources) == {"thermal-03", "cam-07"}


def test_stale_reading_is_untrusted(validator, now):
    stale = now - timedelta(seconds=120)
    ev = validator.evaluate_reading(
        _reading("thermal-03", SensorType.THERMAL, 80.0, stale)
    )
    assert ev.verdict is ReadingVerdict.UNTRUSTED
    assert any(r.startswith("STALE_READING") for r in ev.reasons)


def test_out_of_physical_range_reading_is_untrusted(validator, now):
    # 温感被伪造到物理不可能的 200℃，直接丧失仲裁资格
    ev = validator.evaluate_reading(
        _reading("thermal-03", SensorType.THERMAL, 200.0, now)
    )
    assert ev.verdict is ReadingVerdict.UNTRUSTED
    assert any("OUT_OF_PHYSICAL_RANGE" in r for r in ev.reasons)


def test_conflicting_sources_escalate(validator, now):
    # 视觉报火但温感显示 35℃ 常温：典型对抗贴纸/冷气假正常，矛盾即升级
    readings = [
        _reading("cam-07", SensorType.VISION_FIRE, True, now),
        _reading("thermal-03", SensorType.THERMAL, 35.0, now),
    ]
    result = validator.arbitrate(readings, scenario="fire_alarm")
    assert result.action is ArbitrationAction.ESCALATE
    assert result.conflicting_sources == ("thermal-03",)


def test_self_test_reading_is_isolated(validator, now):
    ev = validator.evaluate_reading(
        _reading("thermal-03", SensorType.THERMAL, 80.0, now, is_self_test=True)
    )
    assert ev.verdict is ReadingVerdict.SELF_TEST

    readings = [
        _reading("thermal-03", SensorType.THERMAL, 80.0, now, is_self_test=True),
        _reading("cam-07", SensorType.VISION_FIRE, True, now),
    ]
    result = validator.arbitrate(readings, scenario="fire_alarm")
    assert "thermal-03" in result.untrusted_sources
    # 自检读数不得参与确认，视觉仍只有单源
    assert result.action is ArbitrationAction.ALERT


def test_suppression_guard_forces_escalation(validator):
    assert validator.suppression_guard("rack-03", 2) is None
    decision = validator.suppression_guard("rack-03", 3)
    assert decision is not None
    assert decision.allowed is False
    assert "强制人工升级" in decision.reasons[0]


def test_rate_change_anomaly_marks_suspect(validator, now):
    first = _reading("thermal-03", SensorType.THERMAL, 40.0, now)
    later = _reading(
        "thermal-03", SensorType.THERMAL, 90.0, now + timedelta(seconds=10)
    )
    validator.evaluate_reading(first)
    ev = validator.evaluate_reading(later)
    assert ev.verdict is ReadingVerdict.SUSPECT
    assert any("RATE_CHANGE_ANOMALY" in r for r in ev.reasons)
    assert ev.adjusted_confidence < 1.0


def test_rate_change_with_hvac_event_is_trusted(validator, now):
    validator.evaluate_reading(
        _reading("thermal-03", SensorType.THERMAL, 40.0, now)
    )
    ev = validator.evaluate_reading(
        _reading(
            "thermal-03",
            SensorType.THERMAL,
            90.0,
            now + timedelta(seconds=10),
            metadata={"hvac_event": True},
        )
    )
    assert ev.verdict is ReadingVerdict.TRUSTED


def test_overheat_and_policy(validator, now):
    readings = [
        _reading("thermal-03", SensorType.THERMAL, 70.0, now),
        _reading("smoke-03", SensorType.SMOKE_SENSOR, True, now),
    ]
    result = validator.arbitrate(
        readings, scenario="overheat", proposed_action="circuit.break"
    )
    assert result.action is ArbitrationAction.DESTRUCTIVE_ALLOWED


def test_overheat_and_policy_requires_all_sources(validator, now):
    # 温感过热但烟感正常：AND 不成立且源间矛盾，只能升级不能断电
    readings = [
        _reading("thermal-03", SensorType.THERMAL, 70.0, now),
        _reading("smoke-03", SensorType.SMOKE_SENSOR, False, now),
    ]
    result = validator.arbitrate(
        readings, scenario="overheat", proposed_action="circuit.break"
    )
    assert result.action is ArbitrationAction.DESTRUCTIVE_BLOCKED
    assert result.conflicting_sources == ("smoke-03",)


def test_low_confidence_reading_is_untrusted(validator, now):
    ev = validator.evaluate_reading(
        _reading("cam-07", SensorType.VISION_FIRE, True, now, confidence=0.2)
    )
    assert ev.verdict is ReadingVerdict.UNTRUSTED
    assert "LOW_CONFIDENCE" in ev.reasons


def test_guard_destructive_action_helper(validator, now):
    single = validator.arbitrate(
        [_reading("cam-07", SensorType.VISION_FIRE, True, now)],
        scenario="fire_alarm",
        proposed_action="power.off",
    )
    decision = validator.guard_destructive_action(single, "power.off")
    assert decision is not None and decision.allowed is False

    # 非破坏性动作不受仲裁拦截
    assert validator.guard_destructive_action(single, "robot.task_status") is None

"""L3 多模态多源交叉验证器。

覆盖机房巡检机器人 / 视觉烟火 / 红外温感联动的现实对抗场景：
- 对抗贴纸、强光闪照骗过视觉       → 单源告警只能 ALERT，破坏性动作须异质多源确认
- 温感伪造（80℃ 改 40℃）、冷气假正常 → 物理边界 + 周期跳变 + 源间矛盾检测，矛盾即升级
- 阈值被远程篡改                   → 阈值固化在基线配置，代码内只认配置值
- 与/或逻辑被改                     → 仲裁策略枚举固定，非法策略直接 fail-closed
- 自检模拟告警被当真/被用来屏蔽     → 自检读数物理隔离，不参与真实仲裁
- 同位置反复过热被自动屏蔽           → 抑制计数器达到上限强制升级人工
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from .loader import BaselineConfig
from .models import (
    ArbitrationAction,
    ArbitrationResult,
    BaselineDecision,
    BaselineLayer,
    ReadingEvaluation,
    ReadingVerdict,
    SensorReading,
    SensorType,
)

logger = logging.getLogger(__name__)

_ALARM_WORDS = {"alarm", "fire", "true", "smoke", "overheat"}


class CrossSourceValidator:
    """多源读数可信度评估与仲裁。"""

    def __init__(self, config: BaselineConfig, *, clock=None) -> None:
        self._config = config
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.RLock()
        # source_id -> 上一周期数值读数，用于周期跳变检测
        self._last_numeric: dict[str, tuple[float, datetime]] = {}

    # ------------------------------------------------------------------
    # 单源可信度评估
    # ------------------------------------------------------------------

    def evaluate_reading(self, reading: SensorReading) -> ReadingEvaluation:
        profile = self._config.sensor_profile(reading.sensor_type.value)
        if not profile:
            return ReadingEvaluation(
                reading=reading,
                verdict=ReadingVerdict.UNTRUSTED,
                reasons=("UNKNOWN_SENSOR_TYPE",),
                adjusted_confidence=0.0,
            )

        if reading.is_self_test:
            return ReadingEvaluation(
                reading=reading,
                verdict=ReadingVerdict.SELF_TEST,
                reasons=("SELF_TEST_ISOLATED",),
                adjusted_confidence=0.0,
            )

        reasons: list[str] = []
        verdict = ReadingVerdict.TRUSTED
        confidence = max(0.0, min(1.0, reading.confidence))

        # 1. 新鲜度：过期读数不具备仲裁资格
        max_stale = float(profile.get("max_staleness_seconds", 30))
        age = (self._clock() - reading.observed_at).total_seconds()
        if age > max_stale:
            reasons.append(f"STALE_READING:{int(age)}s>{max_stale}s")
            return ReadingEvaluation(reading, ReadingVerdict.UNTRUSTED, tuple(reasons), 0.0)

        # 2. 置信度下限
        if confidence < float(profile.get("min_confidence", 0.5)):
            reasons.append("LOW_CONFIDENCE")
            return ReadingEvaluation(reading, ReadingVerdict.UNTRUSTED, tuple(reasons), 0.0)

        # 3. 物理边界与周期跳变（仅数值型温感）
        if reading.sensor_type is SensorType.THERMAL and isinstance(reading.value, (int, float)):
            value = float(reading.value)
            low, high = float(profile["physical_min"]), float(profile["physical_max"])
            if not low <= value <= high:
                reasons.append(f"OUT_OF_PHYSICAL_RANGE:{value}")
                return ReadingEvaluation(reading, ReadingVerdict.UNTRUSTED, tuple(reasons), 0.0)

            with self._lock:
                previous = self._last_numeric.get(reading.source_id)
                self._last_numeric[reading.source_id] = (value, reading.observed_at)
            if previous is not None:
                prev_value, prev_time = previous
                max_change = float(profile.get("max_change_per_cycle", 25.0))
                if abs(value - prev_value) > max_change and not reading.metadata.get(
                    "hvac_event", False
                ):
                    reasons.append(f"RATE_CHANGE_ANOMALY:{prev_value}->{value}")
                    verdict = ReadingVerdict.SUSPECT
                    confidence *= 0.5

        return ReadingEvaluation(reading, verdict, tuple(reasons), round(confidence, 3))

    # ------------------------------------------------------------------
    # 多源仲裁
    # ------------------------------------------------------------------

    def arbitrate(
        self,
        readings: list[SensorReading],
        *,
        scenario: str = "fire_alarm",
        proposed_action: str | None = None,
    ) -> ArbitrationResult:
        spec = self._config.scenario(scenario)
        policy = str(spec.get("policy", "QUORUM")).upper()
        if policy not in {"AND", "OR", "QUORUM", "WEIGHTED"}:
            # 策略枚举被篡改时 fail-closed，绝不按未知逻辑放行破坏性动作
            raise ValueError(f"非法仲裁策略: {policy}")

        evaluations = [self.evaluate_reading(r) for r in readings]
        usable = [
            e for e in evaluations
            if e.verdict in (ReadingVerdict.TRUSTED, ReadingVerdict.SUSPECT)
        ]
        untrusted = tuple(
            e.reading.source_id
            for e in evaluations
            if e.verdict in (ReadingVerdict.UNTRUSTED, ReadingVerdict.SELF_TEST)
        )

        alarming: dict[SensorType, ReadingEvaluation] = {}
        normal: dict[SensorType, ReadingEvaluation] = {}
        for ev in usable:
            bucket = alarming if self._is_alarming(ev) else normal
            # 同类型多源时保留置信度更高者
            current = bucket.get(ev.reading.sensor_type)
            if current is None or ev.adjusted_confidence > current.adjusted_confidence:
                bucket[ev.reading.sensor_type] = ev

        alarm_types = set(alarming)
        normal_types = set(normal)
        conflicting = tuple(
            sorted(t.source_id for t in (e.reading for e in normal.values()))
            if alarm_types and normal_types else ()
        )
        required_types = int(spec.get("required_distinct_types", 2))
        destructive_min = int(spec.get("destructive_min_types", 2))

        confirmed = self._apply_policy(policy, spec, alarming, usable)
        reasons: list[str] = []
        if conflicting:
            reasons.append("SOURCE_CONFLICT:告警源与正常源并存，疑似伪造或对抗干扰")
        if not confirmed and alarm_types and len(alarm_types) < required_types:
            reasons.append(f"INSUFFICIENT_SOURCES:{len(alarm_types)}<{required_types}")

        weighted_confidence = self._weighted_confidence(alarming)
        agreeing = tuple(sorted(e.reading.source_id for e in alarming.values()))

        is_destructive = (
            proposed_action is not None
            and proposed_action in self._config.destructive_actions
        )

        if is_destructive:
            allowed = (
                confirmed
                and len(alarm_types) >= destructive_min
                and not conflicting
            )
            if allowed:
                action = ArbitrationAction.DESTRUCTIVE_ALLOWED
                reasons.insert(0, f"DESTRUCTIVE_CONFIRMED:{proposed_action}")
            else:
                action = ArbitrationAction.DESTRUCTIVE_BLOCKED
                reasons.insert(0, f"DESTRUCTIVE_DENIED:{proposed_action}")
        elif conflicting:
            action = ArbitrationAction.ESCALATE
        elif confirmed:
            action = ArbitrationAction.ALERT
            reasons.insert(0, "MULTI_SOURCE_CONFIRMED")
        elif alarm_types:
            # 单源告警：提示但不升级处置，等待第二源交叉确认
            action = ArbitrationAction.ALERT
            reasons.insert(0, "SINGLE_SOURCE_UNCONFIRMED")
        else:
            action = ArbitrationAction.NO_ACTION

        result = ArbitrationResult(
            action=action,
            scenario=scenario,
            confidence=round(weighted_confidence, 3),
            agreeing_sources=agreeing,
            conflicting_sources=conflicting,
            untrusted_sources=untrusted,
            reasons=tuple(reasons),
            allowed_destructive=action is ArbitrationAction.DESTRUCTIVE_ALLOWED,
        )
        if result.blocked:
            logger.warning("baseline.multimodal.%s sources=%s", action.value, reasons)
        return result

    def guard_destructive_action(
        self,
        result: ArbitrationResult,
        action: str,
    ) -> BaselineDecision | None:
        """把仲裁结论转成基线闸门决策：破坏性动作未获多源确认即拦截升级。"""
        if action not in self._config.destructive_actions:
            return None
        if result.allowed_destructive:
            return None
        return BaselineDecision.escalate(
            reason=f"L3: 破坏性动作 {action} 未通过多源仲裁（{';'.join(result.reasons)}）",
            layer=BaselineLayer.L3_MULTIMODAL,
            evidence=result.agreeing_sources or result.untrusted_sources,
        )

    # ------------------------------------------------------------------
    # 告警抑制保护
    # ------------------------------------------------------------------

    def suppression_guard(
        self,
        location: str,
        consecutive_alarm_count: int,
    ) -> BaselineDecision | None:
        """同位置反复告警时禁止自动屏蔽/自愈结案，强制升级。

        对应风险：Agent 把历史自愈成功当规则，对反复过热不再升级直到烧穿。
        """
        limit = self._config.auto_suppression_limit
        if consecutive_alarm_count >= limit:
            return BaselineDecision.escalate(
                reason=(
                    f"L3: 位置 {location} 连续告警 {consecutive_alarm_count} 次"
                    f"达上限 {limit}，禁止自动抑制，强制人工升级"
                ),
                layer=BaselineLayer.L3_MULTIMODAL,
                evidence=(location,),
            )
        return None

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _is_alarming(self, ev: ReadingEvaluation) -> bool:
        value = ev.reading.value
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            profile = self._config.sensor_profile(ev.reading.sensor_type.value)
            threshold = float(profile.get("alarm_threshold", 65.0))
            return float(value) >= threshold
        if isinstance(value, str):
            return value.strip().lower() in _ALARM_WORDS
        return False

    def _apply_policy(self, policy, spec, alarming, usable) -> bool:
        alarm_types = set(alarming)
        required = int(spec.get("required_distinct_types", 2))
        if not alarm_types:
            return False
        if policy == "OR":
            return True
        if policy == "AND":
            return (
                len(alarm_types) >= required
                and alarm_types == {e.reading.sensor_type for e in usable}
                and len(usable) >= required
            )
        if policy == "QUORUM":
            return len(alarm_types) >= required
        # WEIGHTED
        threshold = float(spec.get("weighted_threshold", 1.5))
        total = 0.0
        for ev in alarming.values():
            profile = self._config.sensor_profile(ev.reading.sensor_type.value)
            total += float(profile.get("weight", 1.0)) * ev.adjusted_confidence
        return total >= threshold and len(alarm_types) >= required

    def _weighted_confidence(self, alarming: dict) -> float:
        if not alarming:
            return 0.0
        total = 0.0
        for ev in alarming.values():
            profile = self._config.sensor_profile(ev.reading.sensor_type.value)
            total += float(profile.get("weight", 1.0)) * ev.adjusted_confidence
        return min(1.0, total)

"""机器人物理动作守卫：把 L0/L1/L3 基线接到巡检机器人链路。

覆盖两类入口：
1. 语音/文本指令（robot.voice_command）——先过注入与合规，再识别破坏性意图；
   自由文本永远不能单独授权断电/灭火，必须走多源仲裁。
2. 告警联动的破坏性动作（power.off/circuit.break/fire_suppression.release/
   dr.switchover）——只有 CrossSourceValidator 多源确认后才放行。

所有拦截/放行都通过引擎审计发射点落 baseline 审计事件。
"""

from __future__ import annotations

import re

from .models import (
    BaselineDecision,
    BaselineLayer,
    GateAction,
    SensorReading,
)

# 中文物理控制关键词 → baseline.yaml 中的破坏性动作标识
_DESTRUCTIVE_KEYWORDS: dict[str, str] = {
    "断电": "power.off",
    "停电": "power.off",
    "关机": "power.off",
    "拉闸": "circuit.break",
    "跳闸": "circuit.break",
    "断开断路器": "circuit.break",
    "灭火": "fire_suppression.release",
    "消防喷放": "fire_suppression.release",
    "气体灭火": "fire_suppression.release",
    "灾备切换": "dr.switchover",
    "切换灾备": "dr.switchover",
}


class RobotActionGuard:
    """机器人指令与物理动作的基线守卫。"""

    def __init__(self, engine) -> None:
        self._engine = engine
        actions = sorted(engine.config.destructive_actions)
        # 同时识别中文关键词与字面动作 ID（如 "power.off"）
        self._destructive_pattern = re.compile(
            "|".join(
                [re.escape(k) for k in _DESTRUCTIVE_KEYWORDS]
                + [re.escape(a) for a in actions]
            )
        )

    # ------------------------------------------------------------------
    # 语音/文本指令入口
    # ------------------------------------------------------------------

    def screen_voice_command(self, device_key: str, text: str) -> BaselineDecision:
        """语音指令三级筛查：注入 → 合规 → 破坏性意图。"""
        injection = self._engine.evaluate_input(text)
        if not injection.allowed:
            return injection

        compliance = self._engine.compliance.check(command=text)
        if compliance is not None:
            return compliance

        hit = self._destructive_pattern.search(text)
        if hit is not None:
            action = _DESTRUCTIVE_KEYWORDS.get(hit.group(0), hit.group(0))
            decision = BaselineDecision.escalate(
                reason=(
                    f"L3: 语音指令含破坏性动作 {action}，自由文本不得直接授权，"
                    "须经多源仲裁（arbitrate_sensors）确认后执行"
                ),
                layer=BaselineLayer.L3_MULTIMODAL,
                evidence=(device_key, hit.group(0)),
            )
            self._engine.emit_event(
                "multimodal.escalation",
                layer=BaselineLayer.L3_MULTIMODAL,
                decision=GateAction.ESCALATE.value,
                reasons=decision.reasons,
                evidence=decision.evidence,
                tool_name="robot.voice_command",
                extra={"device_key": device_key},
            )
            return decision

        return BaselineDecision.allow(BaselineLayer.L3_MULTIMODAL)

    # ------------------------------------------------------------------
    # 告警联动的破坏性动作入口
    # ------------------------------------------------------------------

    def authorize_destructive(
        self,
        action: str,
        readings: list[SensorReading],
        *,
        scenario: str = "fire_alarm",
    ) -> BaselineDecision:
        """多源仲裁通过才放行物理破坏性动作，否则升级人工并审计。"""
        result = self._engine.arbitrate_sensors(
            readings,
            scenario=scenario,
            proposed_action=action,
        )
        decision = self._engine.guard_destructive_action(result, action)
        if decision is not None:
            self._engine.emit_event(
                "multimodal.escalation",
                layer=BaselineLayer.L3_MULTIMODAL,
                decision=GateAction.ESCALATE.value,
                reasons=decision.reasons,
                evidence=decision.evidence,
                extra={"action": action, "scenario": scenario},
            )
            return decision

        allowed = BaselineDecision(
            allowed=True,
            action=GateAction.ALLOW,
            reasons=("MULTI_SOURCE_CONFIRMED",),
            layer=BaselineLayer.L3_MULTIMODAL,
            evidence=result.agreeing_sources,
        )
        self._engine.emit_event(
            "multimodal.destructive_allowed",
            layer=BaselineLayer.L3_MULTIMODAL,
            decision=GateAction.ALLOW.value,
            reasons=allowed.reasons,
            evidence=allowed.evidence,
            extra={"action": action, "scenario": scenario},
        )
        return allowed

    def guard_suppression(self, location: str, consecutive_alarm_count: int) -> BaselineDecision | None:
        """同位置反复告警的自动抑制保护，命中即升级并审计。"""
        decision = self._engine.check_suppression(location, consecutive_alarm_count)
        if decision is not None:
            self._engine.emit_event(
                "multimodal.escalation",
                layer=BaselineLayer.L3_MULTIMODAL,
                decision=GateAction.ESCALATE.value,
                reasons=decision.reasons,
                evidence=decision.evidence,
                extra={"location": location, "count": consecutive_alarm_count},
            )
        return decision


__all__ = ["RobotActionGuard"]

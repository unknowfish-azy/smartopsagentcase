"""执行策略映射（P3）：定级 L0~L4 → 执行路线。

AgentForge 语义：L0 直答（单子 agent）、L2+ 规划师生成编排；
本实现映射为 direct / single_tool / plan / dag 四种模式，
L4（ultra 多路择优）本版本预留，路由到 dag。
"""

from __future__ import annotations

from dataclasses import dataclass

from .complexity import ComplexityLevel, ComplexityVerdict


class RouteMode:
    DIRECT = "direct"          # 单轮直答（寒暄/危机话术/被拦截），不进执行器
    SINGLE_TOOL = "single_tool"  # 单 agent 单工具
    PLAN = "plan"              # 线性计划编排（走 PlanRunner 闭环）
    DAG = "dag"                # DAG 并行编排（依赖调度 + 并发上限）


@dataclass
class ExecutionRoute:
    """路由裁决：级别 + 模式 + 说明。"""

    level: str
    mode: str
    reason: str
    verdict: ComplexityVerdict | None = None

    # 危机/注入直通时的固定回复内容
    direct_reply: str | None = None

    def to_dict(self) -> dict:
        result = {
            "level": self.level,
            "mode": self.mode,
            "reason": self.reason,
        }
        if self.verdict is not None:
            result["verdict"] = self.verdict.to_dict()
        return result


def route(verdict: ComplexityVerdict) -> ExecutionRoute:
    """定级 → 执行路线。"""

    level = verdict.level

    if verdict.crisis:
        return ExecutionRoute(
            level=level, mode=RouteMode.DIRECT,
            reason="危机信号直通安全话术，不进入执行器",
            verdict=verdict, direct_reply=CRISIS_REPLY,
        )
    if verdict.injection is not None and verdict.injection.blocked:
        return ExecutionRoute(
            level=level, mode=RouteMode.DIRECT,
            reason="注入风险 HIGH 拦截，不进入执行器",
            verdict=verdict,
            direct_reply=INJECTION_REPLY,
        )
    if verdict.small_talk:
        return ExecutionRoute(
            level=level, mode=RouteMode.DIRECT,
            reason="寒暄直答",
            verdict=verdict,
        )
    if level == ComplexityLevel.SINGLE_TOOL:
        return ExecutionRoute(level=level, mode=RouteMode.SINGLE_TOOL,
                              reason="单工具即可完成，跳过规划器", verdict=verdict)
    if level == ComplexityLevel.PLAN:
        return ExecutionRoute(level=level, mode=RouteMode.PLAN,
                              reason="多步线性计划编排", verdict=verdict)
    if level in (ComplexityLevel.DAG, ComplexityLevel.ULTRA):
        mode = RouteMode.DAG if level == ComplexityLevel.DAG else RouteMode.PLAN
        note = "多路并行 DAG 编排" if level == ComplexityLevel.DAG \
            else "L4 ultra 本版本未启用，按线性计划处理"
        return ExecutionRoute(level=level, mode=mode, reason=note, verdict=verdict)
    return ExecutionRoute(level=level, mode=RouteMode.DIRECT,
                          reason="简单任务直答", verdict=verdict)


CRISIS_REPLY = (
    "我注意到你可能正经历很难的时刻。你的感受很重要，"
    "建议尽快联系专业支持：全国心理援助热线 12356（24 小时），"
    "或前往就近医院心理科。我是运维助手，无法替代专业帮助，但你值得被认真对待。"
)

INJECTION_REPLY = "该请求包含疑似注入攻击的指令模式，已被安全护栏拦截。如有正常需求，请换一种表述方式。"


__all__ = [
    "RouteMode",
    "ExecutionRoute",
    "route",
    "CRISIS_REPLY",
    "INJECTION_REPLY",
]

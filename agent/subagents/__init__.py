"""垂直子智能体：日志诊断 + 巡检。

子智能体只产出预置 DAG 模板，执行复用 agent.executor，
计划校验复用 agent.planner.dag，工具能力以 ToolRegistry 为准。
"""

from .base import SubAgent, SubAgentPlanner, SubAgentRegistry, SubAgentSpec
from .log_diagnosis import LogDiagnosisAgent
from .patrol import PatrolAgent


def default_registry() -> SubAgentRegistry:
    """默认注册表：日志诊断 + 巡检。"""

    return SubAgentRegistry([LogDiagnosisAgent(), PatrolAgent()])


__all__ = [
    "SubAgentSpec",
    "SubAgent",
    "SubAgentRegistry",
    "SubAgentPlanner",
    "LogDiagnosisAgent",
    "PatrolAgent",
    "default_registry",
]

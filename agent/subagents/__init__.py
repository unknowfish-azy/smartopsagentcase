"""垂直子智能体：日志诊断 + 巡检。

子智能体只产出预置 DAG 模板，执行复用 agent.executor，
计划校验复用 agent.planner.dag，工具能力以 ToolRegistry 为准。
"""

from .base import SubAgent, SubAgentPlanner, SubAgentRegistry, SubAgentSpec
from .debate import (
    DEBATE_ROLES,
    DEBATE_ROLE_NAMES,
    Conclusion,
    DebateRecord,
    DebateRunner,
    Rebuttal,
    RoleAgent,
    Verdict,
)
from .evidence_channels import (
    CHANNEL_PROBE_TYPES,
    CHANNEL_ROLES,
    CHANNEL_TOOL_NAMES,
    ChannelView,
    EvidenceItem,
    IsolationReport,
    partition_items,
    shared_pool_views,
    validate_isolation,
)
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
    "DEBATE_ROLES",
    "DEBATE_ROLE_NAMES",
    "Conclusion",
    "Rebuttal",
    "Verdict",
    "DebateRecord",
    "RoleAgent",
    "DebateRunner",
    "CHANNEL_ROLES",
    "CHANNEL_PROBE_TYPES",
    "CHANNEL_TOOL_NAMES",
    "EvidenceItem",
    "ChannelView",
    "IsolationReport",
    "partition_items",
    "shared_pool_views",
    "validate_isolation",
]

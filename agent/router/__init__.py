"""复杂度路由（P3）：定级 → 执行策略映射。

蒸馏自 AgentForge（B 站 BV1vxsw68ESP）的五级复杂度路由机制。
"""

from agent.router.complexity import (
    CRISIS_RESPONSE,
    ComplexityLevel,
    ComplexityRouter,
    ComplexityVerdict,
)
from agent.router.policy import (
    CRISIS_REPLY,
    INJECTION_REPLY,
    ExecutionRoute,
    RouteMode,
    route,
)

__all__ = [
    "ComplexityLevel",
    "ComplexityRouter",
    "ComplexityVerdict",
    "CRISIS_RESPONSE",
    "RouteMode",
    "ExecutionRoute",
    "route",
    "CRISIS_REPLY",
    "INJECTION_REPLY",
]

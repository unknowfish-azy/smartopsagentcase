"""L2 运维操作红线检查器。

定位：比 agent.policies.risk.RiskClassifier 更细的参数级闸门，
在 PolicyEngine 风险审批之前执行，命中即短路，不进入审批流程。
"""

from __future__ import annotations

import logging

from .loader import BaselineConfig
from .models import BaselineDecision, BaselineLayer
from .rules import RegexRuleGate

logger = logging.getLogger(__name__)


class RedlineChecker:
    """运维破坏性命令/操作红线。"""

    def __init__(self, config: BaselineConfig) -> None:
        self._gate = RegexRuleGate(config.rules(BaselineLayer.L2_OPERATIONS))

    def check(
        self,
        *,
        command: str = "",
        operation: str = "",
    ) -> BaselineDecision | None:
        """命中红线返回 BLOCK 决策；未命中返回 None 交由后续闸门。"""
        rule = self._gate.match_operation(operation) or self._gate.match_text(command)
        if rule is None:
            return None

        logger.warning(
            "baseline.redline_hit rule=%s operation=%s",
            rule.id,
            operation or command[:80],
        )
        return BaselineDecision.block(
            reason=f"{rule.id}: {rule.message}",
            layer=BaselineLayer.L2_OPERATIONS,
            risk=rule.risk,
            evidence=(rule.name,),
        )

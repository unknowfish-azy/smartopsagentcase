"""L0 合规红线检查器。

合规红线是法律硬边界（网络安全法/刑法/著作权法），与运维红线的区别：
1. 命中后不允许人工审批豁免（baseline.yaml 中 approval_exemptible=false）；
2. 决策必须携带法律依据，直接作为审计证据；
3. 在所有闸门中优先级最高，先于 L2/L1 执行。
"""

from __future__ import annotations

import logging

from .loader import BaselineConfig
from .models import BaselineDecision, BaselineLayer
from .rules import RegexRuleGate

logger = logging.getLogger(__name__)


class ComplianceGuard:
    """未授权扫描/逆向/破解/嗅探/穿透/木马/反爬绕过的硬红线。"""

    def __init__(self, config: BaselineConfig) -> None:
        self._gate = RegexRuleGate(config.rules(BaselineLayer.L0_COMPLIANCE))
        layer_cfg = config.layer_config(BaselineLayer.L0_COMPLIANCE)
        self.approval_exemptible = bool(layer_cfg.get("approval_exemptible", False))

    def check(self, *, command: str = "", operation: str = "") -> BaselineDecision | None:
        rule = self._gate.match_text(command) or self._gate.match_operation(operation)
        if rule is None:
            return None

        logger.warning(
            "baseline.compliance_hit rule=%s legal_ref=%s",
            rule.id,
            rule.legal_ref,
        )
        reason = f"{rule.id}: {rule.message}（依据：{rule.legal_ref}）"
        return BaselineDecision.block(
            reason=reason,
            layer=BaselineLayer.L0_COMPLIANCE,
            risk=rule.risk,
            evidence=(rule.id, rule.legal_ref),
        )

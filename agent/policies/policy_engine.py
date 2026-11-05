from .models import PolicyDecision
from .risk import RiskClassifier, RiskLevel


class PolicyEngine:

    def __init__(
        self,
        risk_classifier=None,
        *,
        approval_manager=None,
    ):
        self.risk_classifier = (
            risk_classifier
            or RiskClassifier()
        )
        self.approval_manager = approval_manager

    def _risk(self, tool):
        levels = list(RiskLevel)
        classified = RiskLevel(self.risk_classifier.classify(tool.name))
        try:
            declared = RiskLevel(str(getattr(tool.risk_level, "value", tool.risk_level)).upper())
        except (ValueError, AttributeError):
            # Unknown declared risk never lowers the classifier's requirement.
            declared = RiskLevel.CRITICAL
        return max((classified, declared), key=levels.index)

    def _requires_approval(self, tool, step):
        return self._risk(tool) == RiskLevel.HIGH or bool(tool.requires_approval) or bool(step.requires_approval)

    def check(
        self,
        tool,
        context,
        step,
    ) -> PolicyDecision:

        if tool.name != step.tool_name:
            return PolicyDecision(allowed=False, reason="工具与计划不一致")
        risk = self._risk(tool)

        if risk == RiskLevel.CRITICAL:
            return PolicyDecision(
                allowed=False,
                reason=(
                    "CRITICAL 风险操作禁止由 Agent "
                    "自动执行"
                ),
            )

        if (
            self._requires_approval(tool, step)
            and (self.approval_manager is None or not self.approval_manager.validate(context.approval_id, context, step))
        ):
            return PolicyDecision(
                allowed=False,
                reason=(
                    "高风险操作必须经过人工审批"
                ),
                requires_approval=True,
            )

        return PolicyDecision(
            allowed=True,
            reason="策略允许执行",
        )

    def authorize_execution(self, tool, context, step):
        """Consume once immediately before execution; check() alone is read-only."""
        decision = self.check(tool, context, step)
        if not decision.allowed or context.dry_run or not self._requires_approval(tool, step):
            return decision
        if not self.approval_manager.validate(context.approval_id, context, step, consume=True):
            return PolicyDecision(allowed=False, reason="批准已使用、失效或执行参数不匹配", requires_approval=True)
        return decision

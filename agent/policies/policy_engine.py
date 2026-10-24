from .models import PolicyDecision
from .risk import RiskClassifier, RiskLevel


class PolicyEngine:

    def __init__(
        self,
        risk_classifier=None,
    ):
        self.risk_classifier = (
            risk_classifier
            or RiskClassifier()
        )

    def check(
        self,
        tool,
        context,
        step,
    ) -> PolicyDecision:

        risk = self.risk_classifier.classify(
            tool.name
        )

        if risk == RiskLevel.CRITICAL:
            return PolicyDecision(
                allowed=False,
                reason=(
                    "CRITICAL 风险操作禁止由 Agent "
                    "自动执行"
                ),
            )

        if (
            risk == RiskLevel.HIGH
            and not step.requires_approval
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
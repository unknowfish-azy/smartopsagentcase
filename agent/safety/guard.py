from agent.policies.risk import RiskLevel

from .decision import SafetyDecision


class SafetyGuard:

    def evaluate(
        self,
        *,
        permission_granted: bool,
        risk: RiskLevel,
        approval_granted: bool = False,
    ) -> SafetyDecision:

        if not permission_granted:
            return SafetyDecision(
                allowed=False,
                requires_approval=False,
                risk=risk,
                reason="Permission denied",
            )

        if risk == RiskLevel.CRITICAL:
            return SafetyDecision(
                allowed=False,
                requires_approval=True,
                risk=risk,
                reason=(
                    "Critical operation blocked"
                ),
            )

        if (
            risk == RiskLevel.HIGH
            and not approval_granted
        ):
            return SafetyDecision(
                allowed=False,
                requires_approval=True,
                risk=risk,
                reason=(
                    "Human approval required"
                ),
            )

        return SafetyDecision(
            allowed=True,
            requires_approval=False,
            risk=risk,
            reason="Operation allowed",
        )
from agent.policies.risk import RiskLevel
from agent.registry.permission_registry import (
    PermissionRegistry,
)
from agent.registry.risk_registry import RiskRegistry

from .decision import SafetyDecision
from .guard import SafetyGuard


class SafeAgent:

    def __init__(
        self,
        permissions: PermissionRegistry,
        risks: RiskRegistry,
        guard: SafetyGuard | None = None,
    ) -> None:

        self.permissions = permissions
        self.risks = risks
        self.guard = guard or SafetyGuard()

    def evaluate_operation(
        self,
        *,
        plugin_id: str,
        resource: str,
        action: str,
        operation: str,
        approval_granted: bool = False,
    ) -> SafetyDecision:

        permission_granted = (
            self.permissions.has(
                resource,
                action,
            )
        )

        manifest = self.risks.get(
            plugin_id
        )

        risk = RiskLevel.MEDIUM

        if manifest:
            risk = manifest.risk_of(
                operation
            )

        return self.guard.evaluate(
            permission_granted=permission_granted,
            risk=risk,
            approval_granted=approval_granted,
        )
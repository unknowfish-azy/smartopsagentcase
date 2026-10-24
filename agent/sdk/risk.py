from dataclasses import dataclass

from agent.policies.risk import RiskLevel


@dataclass(frozen=True)
class OperationRisk:
    operation: str
    risk: RiskLevel
    approval_required: bool = False
    description: str = ""


@dataclass
class RiskManifest:
    plugin_id: str
    operations: list[OperationRisk]

    def get(self, operation: str) -> OperationRisk | None:
        for item in self.operations:
            if item.operation == operation:
                return item

        return None

    def risk_of(self, operation: str) -> RiskLevel:
        item = self.get(operation)

        if item is None:
            return RiskLevel.MEDIUM

        return item.risk
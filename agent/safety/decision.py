from dataclasses import dataclass

from agent.policies.risk import RiskLevel


@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    requires_approval: bool
    risk: RiskLevel
    reason: str
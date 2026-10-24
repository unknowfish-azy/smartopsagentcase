from dataclasses import dataclass


@dataclass
class PolicyDecision:

    allowed: bool

    reason: str = ""

    requires_approval: bool = False
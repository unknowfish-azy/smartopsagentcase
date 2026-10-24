from enum import Enum


class RiskLevel(str, Enum):

    LOW = "LOW"

    MEDIUM = "MEDIUM"

    HIGH = "HIGH"

    CRITICAL = "CRITICAL"


class RiskClassifier:

    HIGH_RISK_ACTIONS = {
        "server.restart",
        "server.stop",
        "server.delete",
        "shell.execute",
    }

    CRITICAL_ACTIONS = {
        "server.delete",
        "database.drop",
    }

    def classify(
        self,
        tool_name: str,
    ) -> RiskLevel:

        if tool_name in self.CRITICAL_ACTIONS:
            return RiskLevel.CRITICAL

        if tool_name in self.HIGH_RISK_ACTIONS:
            return RiskLevel.HIGH

        if tool_name.startswith(
            "server."
        ):
            return RiskLevel.MEDIUM

        return RiskLevel.LOW
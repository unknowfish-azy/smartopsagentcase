"""安全意识（S-Aware）：风险 / 影响 / 约束 / 自省 / 证据 / 止损 六感。

全部由确定性规则生成，模型只负责把结构化简报翻成人话。
"""

from .brief import (
    BRIEF_SCHEMA,
    HUMAN_CONFIDENCE_THRESHOLD,
    SecurityBrief,
    SecurityBriefBuilder,
)
from .intent_risk import (
    IntentRiskAnalyzer,
    IntentRule,
    RiskAssessment,
    coerce_risk,
    max_risk,
    risk_rank,
)
from .narrator import BriefNarrator

__all__ = [
    "BRIEF_SCHEMA",
    "HUMAN_CONFIDENCE_THRESHOLD",
    "BriefNarrator",
    "IntentRiskAnalyzer",
    "IntentRule",
    "RiskAssessment",
    "SecurityBrief",
    "SecurityBriefBuilder",
    "coerce_risk",
    "max_risk",
    "risk_rank",
]

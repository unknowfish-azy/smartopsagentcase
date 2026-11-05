"""
SmartOpsAgent Knowledge Evidence Module.

负责知识检索结果的证据管理、引用生成以及可信度计算。

核心能力：
- Evidence：证据数据模型
- build_evidence：从检索结果构建证据
- build_citations：生成引用信息
- TrustScoreCalculator：计算回答可信度
"""

from .models import Evidence
from .citation import build_evidence, build_citations
from .support import (
    ClaimSupport,
    DedupeResult,
    SupportLabel,
    dedupe_evidences,
    label_claim,
)
from .trust_score import (
    INTERPRETATION,
    SCORE_VERSION,
    L3Advice,
    L3JudgeConfig,
    TrustBreakdown,
    TrustScoreCalculator,
    build_breakdown,
)


__all__ = [
    "Evidence",
    "build_evidence",
    "build_citations",
    "TrustScoreCalculator",
    "TrustBreakdown",
    "build_breakdown",
    "L3JudgeConfig",
    "L3Advice",
    "SCORE_VERSION",
    "INTERPRETATION",
    "SupportLabel",
    "ClaimSupport",
    "DedupeResult",
    "label_claim",
    "dedupe_evidences",
]
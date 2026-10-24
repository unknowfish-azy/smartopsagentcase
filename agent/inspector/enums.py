"""
SmartOps Inspector 枚举定义。

与方案中的分类严格保持一致。
"""

from __future__ import annotations

from enum import Enum


class InspectorTarget(str, Enum):
    """纠察对象类型。"""

    SERVER = "SERVER"
    SERVICE = "SERVICE"
    KNOWLEDGE = "KNOWLEDGE"
    MODEL = "MODEL"
    AGENT = "AGENT"
    SKILL = "SKILL"
    TOOL = "TOOL"
    WORKFLOW = "WORKFLOW"
    SECURITY = "SECURITY"
    SESSION = "SESSION"


class Severity(str, Enum):
    """纠察严重程度。"""

    INFO = "INFO"
    NOTICE = "NOTICE"
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class InspectionCategory(str, Enum):
    """纠察问题类别。"""

    PLANNING = "PLANNING"
    EVIDENCE = "EVIDENCE"
    TOOL = "TOOL"
    RISK = "RISK"
    PERMISSION = "PERMISSION"
    APPROVAL = "APPROVAL"
    VERIFICATION = "VERIFICATION"
    KNOWLEDGE = "KNOWLEDGE"
    MODEL = "MODEL"
    SECURITY = "SECURITY"
    PERFORMANCE = "PERFORMANCE"
    LOOP = "LOOP"
    HALLUCINATION = "HALLUCINATION"
    VERSION = "VERSION"


class InspectionStatus(str, Enum):
    """纠察结论状态。"""

    PASS = "PASS"
    WARN = "WARN"
    VIOLATION = "VIOLATION"
    REJECTED = "REJECTED"


class EvidenceLabel(str, Enum):
    """答案与证据一致性标签。"""

    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    CONTRADICTED = "CONTRADICTED"


__all__ = [
    "InspectorTarget",
    "Severity",
    "InspectionCategory",
    "InspectionStatus",
    "EvidenceLabel",
]

"""智维Agent 安全基线框架。

分层：
    L0_COMPLIANCE  合规红线（法律硬边界，不可审批豁免）
    L1_GENERIC_AI  通用 AI 基线（注入/脱敏/RAG/限流）
    L2_OPERATIONS  运维红线（破坏性命令与操作）
    L3_MULTIMODAL  多模态多源交叉验证（机器人/视觉/温感）

与既有模块的关系：复用 agent.safety 的注入检测/输出审核/审批管理，
新增 L0/L2/L3 硬闸门，经 SecurityBaselineEngine 统一门面接入执行链路，
不修改任何既有模块的行为。
"""

from .audit_rotation import RotatingJsonlAuditSink
from .audit_sink import (
    AuditSink,
    BaselineEvent,
    InMemoryAuditSink,
    JsonlAuditSink,
)
from .bootstrap import (
    DEFAULT_AUDIT_DIR,
    DEFAULT_AUDIT_FILE_NAME,
    DEFAULT_MAX_BYTES,
    SecurityBaselineBundle,
    build_security_baseline,
)
from .compliance import ComplianceGuard
from .engine import SecurityBaselineEngine
from .integrity import (
    PIN_FILE_NAME,
    IntegrityDecision,
    PluginIntegrityGuard,
    compute_directory_hashes,
    generate_pin_file,
    load_pin_file,
    verify_pin_signature,
    write_pin_file,
)
from .loader import BaselineConfig, load_baseline
from .models import (
    ArbitrationAction,
    ArbitrationResult,
    BaselineDecision,
    BaselineLayer,
    BaselineRule,
    GateAction,
    ReadingEvaluation,
    ReadingVerdict,
    SensorReading,
    SensorType,
)
from .multimodal import CrossSourceValidator
from .ratelimit import RateLimitManager, TokenBucket
from .redlines import RedlineChecker
from .robot_guard import RobotActionGuard

__all__ = [
    "SecurityBaselineEngine",
    "SecurityBaselineBundle",
    "build_security_baseline",
    "DEFAULT_AUDIT_DIR",
    "DEFAULT_AUDIT_FILE_NAME",
    "DEFAULT_MAX_BYTES",
    "BaselineConfig",
    "load_baseline",
    "BaselineLayer",
    "GateAction",
    "BaselineDecision",
    "BaselineRule",
    "SensorType",
    "SensorReading",
    "ReadingVerdict",
    "ReadingEvaluation",
    "ArbitrationAction",
    "ArbitrationResult",
    "ComplianceGuard",
    "RedlineChecker",
    "CrossSourceValidator",
    "RateLimitManager",
    "TokenBucket",
    "AuditSink",
    "BaselineEvent",
    "InMemoryAuditSink",
    "JsonlAuditSink",
    "RotatingJsonlAuditSink",
    "RobotActionGuard",
    "IntegrityDecision",
    "PluginIntegrityGuard",
    "PIN_FILE_NAME",
    "generate_pin_file",
    "write_pin_file",
    "load_pin_file",
    "compute_directory_hashes",
    "verify_pin_signature",
]

"""安全基线数据模型。

与现有 agent.policies.risk.RiskLevel / agent.safety.decision.SafetyDecision 同构，
但基线决策额外携带分层标识（L0~L3）与证据链，便于审计归因。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime

from agent.policies.risk import RiskLevel


class BaselineLayer(str, enum.Enum):
    """基线分层。"""

    L0_COMPLIANCE = "L0_COMPLIANCE"
    L1_GENERIC_AI = "L1_GENERIC_AI"
    L2_OPERATIONS = "L2_OPERATIONS"
    L3_MULTIMODAL = "L3_MULTIMODAL"


class GateAction(str, enum.Enum):
    """基线闸门动作。"""

    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REDACT = "REDACT"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    ESCALATE = "ESCALATE"
    QUARANTINE = "QUARANTINE"


@dataclass(frozen=True)
class BaselineDecision:
    """基线评估结论。

    allowed=False 时调用方必须短路执行链；reasons 中的规则 ID 是审计主键。
    """

    allowed: bool
    action: GateAction
    reasons: tuple[str, ...] = ()
    layer: BaselineLayer | None = None
    risk: RiskLevel = RiskLevel.LOW
    redacted_text: str | None = None
    evidence: tuple[str, ...] = ()

    @classmethod
    def allow(cls, layer: BaselineLayer | None = None) -> "BaselineDecision":
        return cls(allowed=True, action=GateAction.ALLOW, layer=layer)

    @classmethod
    def block(
        cls,
        reason: str,
        layer: BaselineLayer,
        *,
        risk: RiskLevel = RiskLevel.CRITICAL,
        evidence: tuple[str, ...] = (),
    ) -> "BaselineDecision":
        return cls(
            allowed=False,
            action=GateAction.BLOCK,
            reasons=(reason,),
            layer=layer,
            risk=risk,
            evidence=evidence,
        )

    @classmethod
    def escalate(
        cls,
        reason: str,
        layer: BaselineLayer,
        *,
        evidence: tuple[str, ...] = (),
    ) -> "BaselineDecision":
        return cls(
            allowed=False,
            action=GateAction.ESCALATE,
            reasons=(reason,),
            layer=layer,
            risk=RiskLevel.HIGH,
            evidence=evidence,
        )


# ---------------------------------------------------------------------------
# L0/L2 规则模型
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BaselineRule:
    """一条声明式红线规则。"""

    id: str
    name: str
    pattern: str
    layer: BaselineLayer
    match: str = "regex"  # regex | operation
    message: str = ""
    risk: RiskLevel = RiskLevel.CRITICAL
    legal_ref: str = ""


# ---------------------------------------------------------------------------
# L3 多模态模型
# ---------------------------------------------------------------------------


class SensorType(str, enum.Enum):
    THERMAL = "thermal"
    VISION_FIRE = "vision_fire"
    VISION_SMOKE = "vision_smoke"
    SMOKE_SENSOR = "smoke_sensor"
    ROBOT_NAV = "robot_nav"


class ReadingVerdict(str, enum.Enum):
    TRUSTED = "TRUSTED"
    SUSPECT = "SUSPECT"          # 跳变异常等，降权参与
    UNTRUSTED = "UNTRUSTED"      # 越界/过期，不参与仲裁
    SELF_TEST = "SELF_TEST"      # 自检读数，与真实链路隔离


class ArbitrationAction(str, enum.Enum):
    NO_ACTION = "NO_ACTION"
    ALERT = "ALERT"
    ESCALATE = "ESCALATE"
    DESTRUCTIVE_ALLOWED = "DESTRUCTIVE_ALLOWED"
    DESTRUCTIVE_BLOCKED = "DESTRUCTIVE_BLOCKED"


@dataclass(frozen=True)
class SensorReading:
    """一次传感器读数。

    value 约定：布尔类传感器（视觉/烟感）传 True/False 表示是否告警；
    温感传摄氏温度数值。observed_at 必须由采集侧打上时间戳。
    """

    source_id: str
    sensor_type: SensorType
    value: float | bool | str
    observed_at: datetime
    confidence: float = 1.0
    location: str = ""
    is_self_test: bool = False
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ReadingEvaluation:
    reading: SensorReading
    verdict: ReadingVerdict
    reasons: tuple[str, ...] = ()
    adjusted_confidence: float = 1.0


@dataclass(frozen=True)
class ArbitrationResult:
    """多源仲裁结论。

    allowed_destructive 是破坏性动作的唯一通行证：False 时
    power.off/circuit.break 等动作必须被拦截并升级人工。
    """

    action: ArbitrationAction
    scenario: str
    confidence: float
    agreeing_sources: tuple[str, ...]
    conflicting_sources: tuple[str, ...]
    untrusted_sources: tuple[str, ...]
    reasons: tuple[str, ...]
    allowed_destructive: bool

    @property
    def blocked(self) -> bool:
        return self.action in (
            ArbitrationAction.ESCALATE,
            ArbitrationAction.DESTRUCTIVE_BLOCKED,
        )

"""安全基线统一门面。

执行链路上的推荐接入顺序（每个环节都是 fail-closed）：

    用户输入   → evaluate_input()          L1 注入检测
    RAG 证据   → rag_source_allowed()      L1 知识源可信门槛
    工具执行前 → evaluate_operation()      L0 合规 → L2 红线 → L1 限流
                 （风险分级与人工审批仍由 agent.policies.PolicyEngine 负责，
                  本引擎只在其前面增加硬闸门，不替换既有审批链）
    多源告警   → arbitrate_sensors()       L3 多源交叉验证
    输出返回前 → review_output()           L1 脱敏与越权承诺改写
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

from agent.policies.risk import RiskLevel
from agent.safety.injection import InjectionDetector
from agent.safety.moderation import OutputModerator

from .audit_sink import AuditSink, BaselineEvent, build_event
from .compliance import ComplianceGuard
from .loader import BaselineConfig, load_baseline
from .models import (
    ArbitrationResult,
    BaselineDecision,
    BaselineLayer,
    GateAction,
    SensorReading,
)
from .multimodal import CrossSourceValidator
from .ratelimit import RateLimitManager
from .redlines import RedlineChecker

logger = logging.getLogger(__name__)


class SecurityBaselineEngine:
    """智维Agent 安全基线引擎（无状态门面 + 可注入检测器）。"""

    def __init__(
        self,
        config_path: str | None = None,
        *,
        injection_detector: InjectionDetector | None = None,
        output_moderator: OutputModerator | None = None,
        audit_sink: AuditSink | None = None,
        clock=None,
    ) -> None:
        self.config: BaselineConfig = load_baseline(config_path)
        self.fail_closed = self.config.fail_closed
        self.compliance = ComplianceGuard(self.config)
        self.redlines = RedlineChecker(self.config)
        self.validator = CrossSourceValidator(
            self.config, clock=clock or (lambda: datetime.now(timezone.utc))
        )
        self.limiter = RateLimitManager(self.config)
        self.injection = injection_detector or InjectionDetector()
        self.moderator = output_moderator or OutputModerator()
        self.audit_sink = audit_sink

    # ------------------------------------------------------------------
    # 审计发射：只记录 baseline.yaml 白名单内的事件类型
    # ------------------------------------------------------------------

    def emit_event(
        self,
        event_type: str,
        *,
        layer: BaselineLayer | str = "",
        decision: str = "",
        reasons: tuple[str, ...] = (),
        evidence: tuple[str, ...] = (),
        request_id: str = "",
        user_id: str = "",
        tool_name: str = "",
        action: str = "",
        extra: dict | None = None,
    ) -> BaselineEvent | None:
        """向审计接收器追加一条白名单事件；未挂 sink 或非白名单时静默跳过。"""
        if self.audit_sink is None or event_type not in self.config.audit_required_events:
            return None
        layer_value = layer.value if isinstance(layer, BaselineLayer) else str(layer)
        event = build_event(
            event_type,
            layer=layer_value,
            decision=decision,
            reasons=reasons,
            evidence=evidence,
            request_id=request_id,
            user_id=user_id,
            tool_name=tool_name,
            action=action,
            extra=extra,
        )
        self.audit_sink.record(event)
        return event

    # ------------------------------------------------------------------
    # L1 输入侧
    # ------------------------------------------------------------------

    def evaluate_input(self, message: str) -> BaselineDecision:
        def _run() -> BaselineDecision:
            if not message:
                return BaselineDecision.allow(BaselineLayer.L1_GENERIC_AI)
            result = self.injection.scan(message)
            block_on = self.config.layer_config(BaselineLayer.L1_GENERIC_AI).get(
                "injection", {}
            ).get("block_on_risk", "HIGH")
            if result.risk_level is RiskLevel[block_on]:
                return BaselineDecision.block(
                    reason=f"INJECTION_BLOCK:{','.join(result.matched_rules) or result.risk_level.value}",
                    layer=BaselineLayer.L1_GENERIC_AI,
                    risk=result.risk_level,
                )
            if result.sanitized_text and result.sanitized_text != message:
                return BaselineDecision(
                    allowed=True,
                    action=GateAction.REDACT,
                    reasons=("INJECTION_SANITIZED",),
                    layer=BaselineLayer.L1_GENERIC_AI,
                    risk=result.risk_level,
                    redacted_text=result.sanitized_text,
                )
            return BaselineDecision.allow(BaselineLayer.L1_GENERIC_AI)

        return self._fail_closed(_run, BaselineLayer.L1_GENERIC_AI)

    def review_output(self, text: str) -> BaselineDecision:
        def _run() -> BaselineDecision:
            result = self.moderator.moderate(text)
            if not result.allowed:
                return BaselineDecision.block(
                    reason=f"OUTPUT_BLOCK:{','.join(result.flags)}",
                    layer=BaselineLayer.L1_GENERIC_AI,
                )
            if result.redacted:
                return BaselineDecision(
                    allowed=True,
                    action=GateAction.REDACT,
                    reasons=tuple(f"PII:{f}" for f in result.flags),
                    layer=BaselineLayer.L1_GENERIC_AI,
                    redacted_text=result.redacted_text,
                )
            return BaselineDecision.allow(BaselineLayer.L1_GENERIC_AI)

        return self._fail_closed(_run, BaselineLayer.L1_GENERIC_AI)

    def rag_source_allowed(self, source: str, trust_score: float) -> BaselineDecision:
        """RAG 知识源门槛：可信分不足或域不在白名单时拒绝其进入召回。"""
        cfg = self.config.layer_config(BaselineLayer.L1_GENERIC_AI).get("rag", {})
        min_trust = float(cfg.get("min_source_trust", 0.6))
        allowed_domains = cfg.get("allowed_source_domains", [])
        domain = urlparse(source).netloc if "://" in source else source
        if trust_score < min_trust:
            return BaselineDecision.block(
                reason=f"RAG_LOW_TRUST:{trust_score}<{min_trust}",
                layer=BaselineLayer.L1_GENERIC_AI,
                evidence=(domain,),
            )
        if allowed_domains and domain not in allowed_domains:
            return BaselineDecision.block(
                reason="RAG_DOMAIN_NOT_ALLOWED",
                layer=BaselineLayer.L1_GENERIC_AI,
                evidence=(domain,),
            )
        return BaselineDecision.allow(BaselineLayer.L1_GENERIC_AI)

    # ------------------------------------------------------------------
    # L0 + L2 + L1 操作闸门
    # ------------------------------------------------------------------

    def evaluate_operation(
        self,
        *,
        tool_name: str,
        action: str = "",
        command: str = "",
        identity: str = "default",
        quota_scope: str = "tool_default",
        consume_quota: bool = True,
    ) -> BaselineDecision:
        """工具执行前硬闸门。

        顺序固定：L0 合规（不可豁免）→ L2 运维红线 → L1 限流。
        通过后调用方继续走既有 PolicyEngine 的风险分级与人工审批。
        dry-run 场景传 consume_quota=False：红线照常拦截，但不消耗真实配额。
        """
        operation = f"{tool_name}.{action}" if action else tool_name

        def _run() -> BaselineDecision:
            decision = self.compliance.check(command=command, operation=operation)
            if decision is not None:
                return decision

            decision = self.redlines.check(command=command, operation=operation)
            if decision is not None:
                return decision

            if consume_quota and not self.limiter.acquire(identity, quota_scope):
                return BaselineDecision.block(
                    reason=f"QUOTA_EXHAUSTED:{identity}:{quota_scope}",
                    layer=BaselineLayer.L1_GENERIC_AI,
                    risk=RiskLevel.MEDIUM,
                )
            return BaselineDecision.allow()

        return self._fail_closed(_run, None)

    # ------------------------------------------------------------------
    # L3 多模态
    # ------------------------------------------------------------------

    def arbitrate_sensors(
        self,
        readings: list[SensorReading],
        *,
        scenario: str = "fire_alarm",
        proposed_action: str | None = None,
    ) -> ArbitrationResult:
        return self.validator.arbitrate(
            readings,
            scenario=scenario,
            proposed_action=proposed_action,
        )

    def guard_destructive_action(
        self,
        result: ArbitrationResult,
        action: str,
    ) -> BaselineDecision | None:
        return self.validator.guard_destructive_action(result, action)

    def check_suppression(
        self, location: str, consecutive_alarm_count: int
    ) -> BaselineDecision | None:
        return self.validator.suppression_guard(location, consecutive_alarm_count)

    # ------------------------------------------------------------------
    # fail-closed 兜底
    # ------------------------------------------------------------------

    def _fail_closed(self, check, layer) -> BaselineDecision:
        try:
            return check()
        except Exception as exc:  # noqa: BLE001 - 护栏异常不得击穿执行链
            logger.exception("baseline.guard_error")
            if self.fail_closed:
                return BaselineDecision.block(
                    reason=f"GUARD_ERROR:{type(exc).__name__}",
                    layer=layer or BaselineLayer.L2_OPERATIONS,
                )
            return BaselineDecision.allow(layer)

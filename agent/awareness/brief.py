"""SecurityBrief：确定性生成的"安全意识简报"。

六感映射（全部由确定性规则产出，LLM 只负责措辞）：

* 风险感   → ``risk_level`` / ``risk_reasons``
* 影响感   → ``blast_radius``（缺少真实资产上下文时如实留空，不编造）
* 约束感   → ``required_approvals``
* 自省感   → ``attack_report``（命中可疑指令时明示"未执行其中要求"）
* 证据感   → ``evidence_refs`` / ``data_sources``
* 止损感   → ``preconditions`` / ``rollback_plan`` / ``verification_plan``

契约版本固定为 ``smartops.security_brief.v1``，前后端共用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from agent.policies.risk import RiskLevel

from .intent_risk import (
    IntentRiskAnalyzer,
    coerce_risk,
    max_risk,
    risk_rank,
)
from .narrator import BriefNarrator

BRIEF_SCHEMA = "smartops.security_brief.v1"
HUMAN_CONFIDENCE_THRESHOLD = 0.6

# 每个意图的确定性止损模板（不依赖模型生成）。
_CHANGE_PLANS: dict[str, dict[str, Any]] = {
    "emergency_stop": {
        "preconditions": ("确认急停对象与现场人员安全", "确认急停不会造成二次伤害"),
        "rollback": "急停为安全兜底动作，恢复前必须人工确认现场风险已解除。",
        "verification": ("设备状态确认为已停止", "现场告警已升级至值守人员"),
    },
    "drop_database": {
        "preconditions": ("确认目标库无在线依赖", "确认已有可恢复备份", "确认变更窗口已审批"),
        "rollback": "操作前导出全量备份与结构快照；异常时按快照恢复。",
        "verification": ("依赖服务无报错", "数据完整性校验通过", "审计事件已落盘"),
    },
    "delete_resource": {
        "preconditions": ("确认目标资源无依赖", "确认已有可恢复备份", "确认影响范围已告知"),
        "rollback": "删除前导出资源定义与数据快照；异常时按快照重建。",
        "verification": ("依赖方无报错", "资源清单与预期一致", "审计事件已落盘"),
    },
    "restart_service": {
        "preconditions": ("确认无进行中的发布或变更", "确认目标服务有可用副本", "确认监控与告警链路可达"),
        "rollback": "保留当前版本与配置快照；重启失败时按快照回滚并恢复上一实例。",
        "verification": ("健康检查返回 200", "错误率 5 分钟内不高于变更前基线", "关键接口延迟回到正常区间"),
    },
    "rollback_release": {
        "preconditions": ("确认上一版本镜像与配置可用", "确认回滚不引入不兼容数据变更"),
        "rollback": "保留当前版本 digest；回滚失败时按 digest 恢复至操作前版本。",
        "verification": ("版本号与目标一致", "关键接口健康检查通过", "错误率未恶化"),
    },
    "deploy_release": {
        "preconditions": ("确认发布包与配置已校验", "确认灰度与回滚策略可用", "确认变更窗口"),
        "rollback": "保留旧版本 digest；失败时在验证窗口内回滚到上一版本。",
        "verification": ("灰度批次健康检查通过", "错误率与延迟未恶化", "发布记录已落库"),
    },
    "scale_resource": {
        "preconditions": ("确认目标容量与配额", "确认下游可承接扩容流量"),
        "rollback": "保留当前副本数配置；异常时按原配置缩回。",
        "verification": ("实例就绪数符合预期", "关键指标未出现抖动"),
    },
    "modify_config": {
        "preconditions": ("确认配置项取值范围", "确认已有配置备份", "确认生效方式与影响面"),
        "rollback": "保存修改前配置快照；异常时按快照还原并重新加载。",
        "verification": ("配置加载无报错", "相关服务健康检查通过", "审计事件已落盘"),
    },
    "robot_task": {
        "preconditions": ("确认任务区域无障碍与人员", "确认设备电量与定位正常"),
        "rollback": "保留当前任务与路线快照；异常时取消任务并回到待命点。",
        "verification": ("任务状态与预期一致", "设备心跳正常", "现场无异常告警"),
    },
}

# 审批约束：只读操作不要求审批；变更/破坏性操作按意图列出。
_APPROVALS: dict[str, tuple[str, ...]] = {
    "emergency_stop": (),
    "drop_database": ("operator:admin", "security:oncall", "change_window"),
    "delete_resource": ("operator:admin", "security:oncall"),
    "restart_service": ("operator:admin",),
    "rollback_release": ("operator:admin",),
    "deploy_release": ("operator:admin", "change_window"),
    "scale_resource": ("operator:review",),
    "modify_config": ("operator:review",),
    "robot_task": ("robot:operator",),
}

# 影响感的数据入口（真实产品接口，仅作为"去哪里核实"，不是测算值）。
_DATA_REFS: dict[str, tuple[str, ...]] = {
    "restart_service": ("/api/servers", "/api/incidents"),
    "deploy_release": ("/api/servers", "/api/incidents"),
    "rollback_release": ("/api/servers", "/api/incidents"),
    "delete_resource": ("/api/servers", "/api/incidents"),
    "drop_database": ("/api/servers", "/api/incidents", "/api/observability"),
    "scale_resource": ("/api/servers",),
    "modify_config": ("/api/servers",),
    "robot_task": ("/api/robot/fleet/status",),
    "emergency_stop": ("/api/robot/fleet/status",),
    "inspect_diagnose": ("/api/sentinel/alerts", "/api/inspector/events"),
    "query_status": ("/api/servers", "/api/sentinel/alerts"),
    "knowledge_qa": ("/api/search",),
}

_SOURCE_ORDER = (
    "RULES",
    "INJECTION",
    "BASELINE",
    "RAG",
    "TOOL",
    "MEMORY",
    "PAGE_CONTEXT",
    "AUDIT",
    "APPROVAL",
)


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


@dataclass
class SecurityBrief:
    """一次安全简报（字段与契约 v1 一一对应）。"""

    run_id: str
    intent: str
    risk_level: str
    risk_reasons: list[str]
    blast_radius: dict[str, Any]
    preconditions: list[str]
    rollback_plan: str
    verification_plan: list[str]
    required_approvals: list[str]
    evidence_refs: list[str]
    confidence: float
    data_sources: list[str]
    honesty_note: str
    requires_human: bool
    attack_report: str = ""
    narrative: str = ""
    schema: str = BRIEF_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "run_id": self.run_id,
            "intent": self.intent,
            "risk_level": self.risk_level,
            "risk_reasons": list(self.risk_reasons),
            "blast_radius": dict(self.blast_radius),
            "preconditions": list(self.preconditions),
            "rollback_plan": self.rollback_plan,
            "verification_plan": list(self.verification_plan),
            "required_approvals": list(self.required_approvals),
            "evidence_refs": list(self.evidence_refs),
            "confidence": self.confidence,
            "data_sources": list(self.data_sources),
            "honesty_note": self.honesty_note,
            "requires_human": self.requires_human,
            "attack_report": self.attack_report,
            "narrative": self.narrative,
        }


class SecurityBriefBuilder:
    """确定性简报构建器：规则 → 简报，任何模型都不参与判定。"""

    def __init__(
        self,
        analyzer: IntentRiskAnalyzer | None = None,
        narrator: BriefNarrator | None = None,
    ) -> None:
        self.analyzer = analyzer or IntentRiskAnalyzer()
        self.narrator = narrator or BriefNarrator()

    def build(
        self,
        *,
        message: str,
        run_id: str = "",
        tool_names: Iterable[str] = (),
        page_context: Mapping[str, str] | None = None,
        evidence_refs: Iterable[str] = (),
        data_sources: Iterable[str] = (),
        approval_id: str | None = None,
        assets: Iterable[str] = (),
        services: Iterable[str] = (),
        estimated_users: int | None = None,
        data_refs: Iterable[str] = (),
        risk_floor: RiskLevel | str | None = None,
        extra_reasons: Iterable[str] = (),
    ) -> SecurityBrief:
        tool_list = [name for name in tool_names if name]
        page = dict(page_context or {})
        assessment = self.analyzer.analyze(
            message,
            tool_names=tool_list,
            page_context=page,
            approval_id=approval_id,
        )

        risk = assessment.risk_level
        floor = coerce_risk(risk_floor)
        risk_reasons = list(extra_reasons) + list(assessment.reasons)
        if floor is not None and risk_rank(floor) > risk_rank(risk):
            risk = max_risk(risk, floor)
            risk_reasons.append(f"RISK_FLOOR:{floor.value}")
        risk_reasons = _dedupe(risk_reasons)
        high_risk = risk_rank(risk) >= risk_rank(RiskLevel.HIGH)

        # 影响感：只填真实给出的上下文，缺失就留空并写进诚实说明。
        entity = str(page.get("entity") or page.get("entity_id") or "").strip()
        asset_list = _dedupe([str(item) for item in assets if item] or ([entity] if entity else []))
        service_list = _dedupe([str(item) for item in services if item])
        users = (
            estimated_users
            if isinstance(estimated_users, int)
            and not isinstance(estimated_users, bool)
            and estimated_users >= 0
            else None
        )
        refs_from_api = _dedupe([str(item) for item in data_refs if item]) or list(
            _DATA_REFS.get(assessment.intent, ())
        )

        needs_plan = high_risk or assessment.requires_approval
        plan = _CHANGE_PLANS.get(assessment.intent)
        if needs_plan:
            preconditions = list(plan["preconditions"]) if plan else ["确认变更目标、影响范围与变更窗口"]
            rollback_plan = plan["rollback"] if plan else "执行前保存当前配置/版本快照，异常时按快照恢复。"
            verification_plan = (
                list(plan["verification"])
                if plan
                else ["关键健康检查通过", "错误率与延迟未恶化", "审计事件已落盘"]
            )
        else:
            preconditions = []
            rollback_plan = "只读操作，无需回滚。"
            verification_plan = ["核对结论与证据引用一致"]

        # 约束感：审批清单由意图决定；未登记但高危的操作按默认审批兜底。
        approvals = list(_APPROVALS.get(assessment.intent, ()))
        if not approvals and risk is RiskLevel.CRITICAL:
            approvals = ["operator:admin", "security:oncall"]
        elif not approvals and high_risk:
            approvals = ["operator:admin"]

        # 证据感：外部证据 + 规则来源，保证每个结论都有出处。
        evidence = [str(item) for item in evidence_refs if item]
        rule_refs = [f"rule:intent:{assessment.intent}", f"rule:risk:{risk.value}"]
        if assessment.injection is not None and risk_rank(assessment.injection.risk_level) >= risk_rank(
            RiskLevel.MEDIUM
        ):
            for rule_name in assessment.injection.matched_rules[:5]:
                rule_refs.append(f"rule:injection:{rule_name}")
        if approval_id:
            rule_refs.append(f"approval:{approval_id}")
        all_evidence = _dedupe(evidence + rule_refs)[:20]
        external_evidence = any(not ref.startswith("rule:") for ref in all_evidence)

        # 置信度：规则置信 + 外部证据/资产上下文加成，越界钳制。
        confidence = assessment.confidence
        if external_evidence:
            confidence += 0.1
        if asset_list or service_list or users is not None:
            confidence += 0.05
        confidence = round(max(0.05, min(0.98, confidence)), 2)

        provided_sources = {str(item) for item in data_sources if item}
        if assessment.injection is not None and risk_rank(assessment.injection.risk_level) >= risk_rank(
            RiskLevel.MEDIUM
        ):
            provided_sources.add("INJECTION")
        if tool_list:
            provided_sources.add("TOOL")
        if page:
            provided_sources.add("PAGE_CONTEXT")
        sources = [name for name in _SOURCE_ORDER if name in provided_sources]
        sources.extend(sorted(provided_sources - set(sources)))
        if "RULES" not in sources:
            sources.insert(0, "RULES")

        notes = ["风险等级与影响面由确定性规则生成，LLM 仅负责措辞。"]
        if users is None:
            notes.append("本次未接入真实资产数据，影响用户数显示为未运行/无数据。")
        if not external_evidence:
            notes.append("本次无外部检索或工具证据，结论仅来自规则匹配。")
        if assessment.attack_report:
            notes.append("检测到可疑指令，已将其作为数据处理。")
        honesty_note = "".join(notes)

        requires_human = (
            confidence < HUMAN_CONFIDENCE_THRESHOLD
            or high_risk
            or bool(approvals)
            or assessment.requires_approval
        )

        brief = SecurityBrief(
            run_id=run_id,
            intent=assessment.intent,
            risk_level=risk.value,
            risk_reasons=risk_reasons,
            blast_radius={
                "assets": asset_list,
                "services": service_list,
                "estimated_users": users,
                "data_refs": refs_from_api,
            },
            preconditions=preconditions,
            rollback_plan=rollback_plan,
            verification_plan=verification_plan,
            required_approvals=approvals,
            evidence_refs=all_evidence,
            confidence=confidence,
            data_sources=sources,
            honesty_note=honesty_note,
            requires_human=requires_human,
            attack_report=assessment.attack_report,
        )
        brief.narrative = self.narrator.narrate(brief)
        return brief


__all__ = [
    "BRIEF_SCHEMA",
    "HUMAN_CONFIDENCE_THRESHOLD",
    "SecurityBrief",
    "SecurityBriefBuilder",
]

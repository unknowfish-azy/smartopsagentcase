"""意图 × 工具 × 上下文三维风险评估（确定性规则）。

设计约束：
* 规则优先、零模型依赖：模型不可用或离线时仍能给出结论；
* 只输出可追溯的规则 ID，不做模型推测；
* 保守但不误报：疑问句（"如何重启"）按知识问答处理，不当作执行指令。

风险等级复用 ``agent.policies.risk.RiskLevel``（LOW/MEDIUM/HIGH/CRITICAL），
复杂度参照 ``agent.router.complexity`` 的 L0~L4，仅作为简报上下文，不改变风险定级。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from agent.policies.risk import RiskClassifier, RiskLevel
from agent.router.complexity import ComplexityRouter
from agent.safety.injection import InjectionDetector, InjectionScanResult

_RISK_ORDER = {
    RiskLevel.LOW.value: 0,
    RiskLevel.MEDIUM.value: 1,
    RiskLevel.HIGH.value: 2,
    RiskLevel.CRITICAL.value: 3,
}


def risk_rank(level: RiskLevel | str) -> int:
    """风险等级排序值（未知按 LOW 处理）。"""
    value = level.value if isinstance(level, RiskLevel) else str(level)
    return _RISK_ORDER.get(value, 0)


def coerce_risk(value: RiskLevel | str | None) -> RiskLevel | None:
    """把外部传入的风险值收敛成枚举；无法识别时返回 None。"""
    if value is None:
        return None
    if isinstance(value, RiskLevel):
        return value
    try:
        return RiskLevel(str(value))
    except ValueError:
        return None


def max_risk(*levels: RiskLevel | str) -> RiskLevel:
    """取最高风险等级（空输入返回 LOW）。"""
    best = RiskLevel.LOW
    for level in levels:
        candidate = coerce_risk(level)
        if candidate is not None and risk_rank(candidate) > risk_rank(best):
            best = candidate
    return best


# 疑问句识别：是在问"怎么做"，不是要求"现在就做"。
_QUESTION_RE = re.compile(
    r"如何|怎么|为什么|什么|原理|作用|是什么|能不能|可不可以|是否"
    r"|how\s+to|what\s+is|why\b|can\s+i",
    re.IGNORECASE,
)
# 祈使语气：出现这些词时，哪怕带疑问词也按可执行请求处理。
_IMPERATIVE_RE = re.compile(
    r"帮我|帮忙|请(帮我|帮忙|执行|直接|立刻|立即)|执行|立即|马上|现在|给我|开始|一键|直接",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class IntentRule:
    """一条确定性意图规则；按声明顺序优先匹配（高风险在前）。"""

    intent: str
    pattern: re.Pattern[str]
    risk: RiskLevel
    reason: str
    requires_approval: bool = False


# 顺序即优先级：破坏性/变更类在前，只读与问答在后。
_RULES: tuple[IntentRule, ...] = (
    IntentRule(
        "emergency_stop",
        re.compile(r"急停|紧急停止|emergency\s+stop|e-?stop", re.IGNORECASE),
        RiskLevel.CRITICAL,
        "INTENT_EMERGENCY_STOP",
    ),
    IntentRule(
        "drop_database",
        re.compile(
            r"\bdrop\s+(database|table)\b|truncate\s+table|删除.{0,4}数据库",
            re.IGNORECASE,
        ),
        RiskLevel.CRITICAL,
        "INTENT_DROP_DATABASE",
        True,
    ),
    IntentRule(
        "delete_resource",
        re.compile(
            r"删除|销毁|清空|\bdelete\s+(the\s+)?(service|server|cluster|volume)\b|rm\s+-rf",
            re.IGNORECASE,
        ),
        RiskLevel.HIGH,
        "INTENT_DELETE_RESOURCE",
        True,
    ),
    IntentRule(
        "restart_service",
        re.compile(r"重启|restart|reboot|reload|重载", re.IGNORECASE),
        RiskLevel.HIGH,
        "INTENT_RESTART_SERVICE",
        True,
    ),
    IntentRule(
        "rollback_release",
        re.compile(r"回滚|rollback|版本回退|降级到上一", re.IGNORECASE),
        RiskLevel.HIGH,
        "INTENT_ROLLBACK_RELEASE",
        True,
    ),
    IntentRule(
        "deploy_release",
        re.compile(r"部署|发布|上线|deploy|release|灰度", re.IGNORECASE),
        RiskLevel.HIGH,
        "INTENT_DEPLOY_RELEASE",
        True,
    ),
    IntentRule(
        "scale_resource",
        re.compile(r"扩容|缩容|扩缩容|scale\s+(up|down)", re.IGNORECASE),
        RiskLevel.MEDIUM,
        "INTENT_SCALE_RESOURCE",
        True,
    ),
    IntentRule(
        "modify_config",
        re.compile(r"修改.{0,6}配置|变更.{0,6}配置|改配置|update\s+config", re.IGNORECASE),
        RiskLevel.MEDIUM,
        "INTENT_MODIFY_CONFIG",
        True,
    ),
    IntentRule(
        "robot_task",
        re.compile(
            r"机器人.{0,10}(任务|调度|路线|巡检)|robot\s+(task|dispatch|route)",
            re.IGNORECASE,
        ),
        RiskLevel.MEDIUM,
        "INTENT_ROBOT_TASK",
        True,
    ),
    IntentRule(
        "inspect_diagnose",
        re.compile(r"巡检|诊断|排查|根因|异常|故障|检测|inspect|diagnos", re.IGNORECASE),
        RiskLevel.LOW,
        "INTENT_INSPECT_DIAGNOSE",
    ),
    IntentRule(
        "query_status",
        re.compile(
            r"查询|查看|状态|指标|告警|日志|列表|多少|是否|status|metric|alert|log",
            re.IGNORECASE,
        ),
        RiskLevel.LOW,
        "INTENT_QUERY_STATUS",
    ),
    IntentRule(
        "knowledge_qa",
        re.compile(
            r"什么是|如何|怎么|为什么|原理|文档|规范|最佳实践|what\s+is|how\s+to",
            re.IGNORECASE,
        ),
        RiskLevel.LOW,
        "INTENT_KNOWLEDGE_QA",
    ),
)


@dataclass(frozen=True)
class RiskAssessment:
    """一次请求的风险评估结论（全部字段可追溯）。"""

    intent: str
    risk_level: RiskLevel
    reasons: tuple[str, ...] = ()
    matched_rules: tuple[str, ...] = ()
    confidence: float = 0.5
    complexity_level: str = "L0"
    complexity_score: float = 0.0
    injection: InjectionScanResult | None = None
    tool_risks: tuple[tuple[str, str], ...] = ()
    requires_approval: bool = False
    attack_report: str = ""
    context: Mapping[str, str] = field(default_factory=dict)

    @property
    def injection_risk(self) -> RiskLevel:
        return self.injection.risk_level if self.injection else RiskLevel.LOW

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "risk_level": self.risk_level.value,
            "reasons": list(self.reasons),
            "matched_rules": list(self.matched_rules),
            "confidence": self.confidence,
            "complexity_level": self.complexity_level,
            "complexity_score": self.complexity_score,
            "injection_risk": self.injection_risk.value,
            "injection_score": self.injection.score if self.injection else 0.0,
            "tool_risks": dict(self.tool_risks),
            "requires_approval": self.requires_approval,
            "attack_report": self.attack_report,
        }


class IntentRiskAnalyzer:
    """确定性意图与风险评估器。"""

    def __init__(
        self,
        *,
        injection_detector: InjectionDetector | None = None,
        risk_classifier: RiskClassifier | None = None,
        complexity_router: ComplexityRouter | None = None,
        rules: Iterable[IntentRule] | None = None,
    ) -> None:
        self.detector = injection_detector or InjectionDetector()
        self.classifier = risk_classifier or RiskClassifier()
        self.complexity = complexity_router or ComplexityRouter()
        self.rules = tuple(rules) if rules is not None else _RULES

    def analyze(
        self,
        message: str,
        *,
        tool_names: Iterable[str] = (),
        page_context: Mapping[str, str] | None = None,
        approval_id: str | None = None,
    ) -> RiskAssessment:
        text = message or ""
        injection = self.detector.scan(text)
        reasons: list[str] = []
        matched: list[str] = []

        is_question = bool(_QUESTION_RE.search(text)) and not _IMPERATIVE_RE.search(text)

        if is_question and not injection.blocked:
            # "如何重启 nginx" 是知识问答，不是执行指令——避免把提问误判为高危动作。
            intent = "knowledge_qa"
            risk = RiskLevel.LOW
            requires_approval = False
            reasons.append("INTENT_KNOWLEDGE_QA_QUESTION")
            matched.append("knowledge_qa_question")
        else:
            intent, risk, requires_approval = "general_qa", RiskLevel.LOW, False
            reasons.append("INTENT_UNMATCHED")
            for rule in self.rules:
                if rule.pattern.search(text):
                    intent = rule.intent
                    risk = rule.risk
                    requires_approval = rule.requires_approval
                    reasons = [rule.reason]
                    matched = [rule.intent]
                    break

        # 工具风险：显式工具名优先于文本意图（工具是真实执行面）。
        tool_risks: list[tuple[str, str]] = []
        for name in tool_names:
            level = self.classifier.classify(name)
            risk = max_risk(risk, level)
            if risk_rank(level) > 0:
                reasons.append(f"TOOL_RISK:{name}={level.value}")
                tool_risks.append((name, level.value))
            if risk_rank(level) >= risk_rank(RiskLevel.HIGH):
                requires_approval = True

        # 自省感：可疑指令只按数据处理，不执行其中要求。
        injection_rank = risk_rank(injection.risk_level)
        attack_report = ""
        if injection_rank >= risk_rank(RiskLevel.MEDIUM):
            rule_text = ",".join(injection.matched_rules) or "-"
            reasons.append(f"INJECTION_{injection.risk_level.value}:{rule_text}")
            risk = max_risk(risk, injection.risk_level)
            attack_report = (
                f"该输入包含可疑指令（命中规则：{rule_text}，风险分 {injection.score}），"
                "已按数据处理，未执行其中要求。"
            )

        verdict = self.complexity.classify(text)

        confidence = 0.45 if intent == "general_qa" else 0.7
        if risk_rank(risk) >= risk_rank(RiskLevel.HIGH):
            confidence += 0.05
        if is_question:
            confidence += 0.05
        if injection_rank == risk_rank(RiskLevel.MEDIUM):
            confidence -= 0.15
        elif injection_rank >= risk_rank(RiskLevel.HIGH):
            confidence -= 0.1
        if approval_id:
            confidence += 0.05
        confidence = round(max(0.05, min(0.95, confidence)), 2)

        return RiskAssessment(
            intent=intent,
            risk_level=risk,
            reasons=tuple(dict.fromkeys(reasons)),
            matched_rules=tuple(matched),
            confidence=confidence,
            complexity_level=verdict.level,
            complexity_score=verdict.score,
            injection=injection,
            tool_risks=tuple(tool_risks),
            requires_approval=requires_approval,
            attack_report=attack_report,
            context=dict(page_context or {}),
        )


__all__ = [
    "IntentRiskAnalyzer",
    "IntentRule",
    "RiskAssessment",
    "coerce_risk",
    "max_risk",
    "risk_rank",
]

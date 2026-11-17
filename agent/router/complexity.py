"""复杂度路由（P3，蒸馏 AgentForge 的五级定级 L0~L4）。

AgentForge 机制：规则快筛（危机/寒暄直通，不调模型）→ 模型打分 → 强度旋钮 → 阈值定级；
简单任务不浪费（单 agent 直答），复杂任务不糊弄（全编排）。

本实现三层结构：
1. ``_triage``   确定性规则快筛：安全拦截（复用 P2 注入检测）、危机信号直通、
   寒暄直答——都不调用模型，零额外成本；
2. ``_score``    模型打分（可注入 score_fn）；模型不可用时降级规则启发式打分，
   链路永远有产出；
3. ``classify``  分数 + 强度旋钮（strength knob）→ 阈值定级 L0~L4。

诚实口径：路由准确率需自建评测集验证后才可对外引用，不得直接引用
AgentForge 的 86.7%（那是它的实测，不是我们的）。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Callable

from agent.safety.injection import InjectionDetector, InjectionScanResult

logger = logging.getLogger(__name__)


class ComplexityLevel:
    """五级复杂度（对齐 AgentForge L0~L4 语义）。"""

    DIRECT = "L0"        # 寒暄/一句话直答，单轮无工具
    SINGLE_TOOL = "L1"   # 单 agent 单工具即可
    PLAN = "L2"          # 多步线性计划编排
    DAG = "L3"           # 多路并行 DAG 编排
    ULTRA = "L4"         # 预留：多路择优 + 校准（本版本不启用，路由到 L3）


# 安全直通：心理危机信号由确定性规则识别，直接给出安抚话术 + 求助指引，
# 不调用模型、不进入任何执行编排（对齐 AgentForge"心理危机信号确定性规则识别"）。
CRISIS_RE = re.compile(
    r"自杀|自残|不想活|轻生|伤害自己|结束生命|suicide|self[-\s]?harm|kill\s+myself",
    re.IGNORECASE,
)
CRISIS_RESPONSE = (
    "我注意到你可能正经历很难的时刻。你的感受很重要，"
    "建议尽快联系专业支持：全国心理援助热线 12356（24 小时），"
    "或前往就近医院心理科。我是运维助手，无法替代专业帮助，但你值得被认真对待。"
)

# 寒暄直答：无任务语义的问候/身份询问，L0 直答，不进规划。
SMALL_TALK_RE = re.compile(
    r"^(你好|您好|hi|hello|嗨|哈喽|在吗|你是谁|你叫什么|谢谢|感谢|再见|拜拜)[\s!！.。?？~]*$",
    re.IGNORECASE,
)

# 启发式打分的复杂度信号词（模型不可用时的降级依据）
_MULTI_TOOL_HINTS = re.compile(
    r"(然后|接着|再|之后|首先|其次|最后|第一步|第二步|并且|同时|依次|流程|每个|所有|批量)",
    re.IGNORECASE,
)
_TOOL_HINTS = re.compile(
    r"(查询|检查|重启|部署|修复|清理|备份|导出|创建|删除|监控|分析|诊断|执行)",
    re.IGNORECASE,
)
_HIGH_RISK_HINTS = re.compile(
    r"(删除|重启|回滚|支付|发布|上线|批量修改|drop|delete|restart|deploy)",
    re.IGNORECASE,
)

# 分数 → 级别阈值（10 分制，对齐 AgentForge"按阈值定级"）
LEVEL_THRESHOLDS = (
    (8.5, ComplexityLevel.DAG),        # ≥8.5 → L3 并行 DAG
    (6.0, ComplexityLevel.PLAN),       # ≥6.0 → L2 线性计划
    (3.0, ComplexityLevel.SINGLE_TOOL) # ≥3.0 → L1 单工具
    # 否则 L0 直答
)


@dataclass
class ComplexityVerdict:
    """定级裁决：级别 + 依据 + 快筛产物。"""

    level: str                     # L0~L4
    score: float                   # 0~10 复杂度分
    scorer: str                    # model / heuristic / triage（打分来源）
    reasons: list[str] = field(default_factory=list)
    injection: InjectionScanResult | None = None
    crisis: bool = False
    small_talk: bool = False
    sanitized_input: str = ""

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "score": self.score,
            "scorer": self.scorer,
            "reasons": self.reasons,
            "crisis": self.crisis,
            "small_talk": self.small_talk,
            "injection_blocked": bool(self.injection and self.injection.blocked),
            "injection_score": self.injection.score if self.injection else 0.0,
        }


class ComplexityRouter:
    """输入 → L0~L4 定级。规则快筛零成本前置，模型打分可注入可降级。

    strength_offset（强度旋钮）：>0 更容易定为复杂（保守派资源），
    <0 更容易定为简单（省钱派）；对齐 AgentForge"强度旋钮的调整"。
    """

    def __init__(
        self,
        score_fn: Callable[[str], float] | None = None,
        injection_detector: InjectionDetector | None = None,
        strength_offset: float = 0.0,
    ) -> None:
        self.score_fn = score_fn
        self.injection_detector = injection_detector or InjectionDetector()
        self.strength_offset = strength_offset

    def classify(self, user_input: str) -> ComplexityVerdict:
        """完整定级入口：快筛 → 打分 → 阈值定级。"""

        reasons: list[str] = []

        # 1) 安全快筛（复用 P2 注入检测——一次规则调用同时完成安全拦截，
        #    对齐 AgentForge"违规请求在复杂度评估时顺带拦截，不增加额外调用"）
        injection = self.injection_detector.scan(user_input)
        if injection.blocked:
            reasons.append(f"注入风险 HIGH（score={injection.score}, rules={injection.matched_rules}）")
            return ComplexityVerdict(
                level=ComplexityLevel.DIRECT,
                score=0.0,
                scorer="triage",
                reasons=reasons,
                injection=injection,
                sanitized_input=injection.sanitized_text,
            )

        sanitized = injection.sanitized_text or user_input

        # 2) 危机信号直通（确定性规则，不调模型）
        if CRISIS_RE.search(sanitized):
            reasons.append("危机信号命中确定性规则，直通安全话术")
            return ComplexityVerdict(
                level=ComplexityLevel.DIRECT,
                score=0.0,
                scorer="triage",
                reasons=reasons,
                injection=injection,
                crisis=True,
                sanitized_input=sanitized,
            )

        # 3) 寒暄直答
        if SMALL_TALK_RE.match(sanitized.strip()):
            reasons.append("寒暄/身份询问，L0 直答")
            return ComplexityVerdict(
                level=ComplexityLevel.DIRECT,
                score=0.0,
                scorer="triage",
                reasons=reasons,
                injection=injection,
                small_talk=True,
                sanitized_input=sanitized,
            )

        # 4) 复杂度打分（模型优先，降级启发式）
        if self.score_fn is not None:
            try:
                raw_score = float(self.score_fn(sanitized))
                raw_score = max(0.0, min(10.0, raw_score))
                reasons.append(f"模型五维打分 {raw_score}")
                scorer = "model"
            except Exception as exc:  # noqa: BLE001 - 打分失败不阻塞路由
                logger.warning("router.score model failed -> heuristic: %s", exc)
                raw_score = self._heuristic_score(sanitized)
                reasons.append(f"模型打分失败降级启发式 {raw_score}")
                scorer = "heuristic"
        else:
            raw_score = self._heuristic_score(sanitized)
            reasons.append(f"启发式打分 {raw_score}（未配置模型评分）")
            scorer = "heuristic"

        # 5) 强度旋钮 + 阈值定级
        score = max(0.0, min(10.0, raw_score + self.strength_offset))
        level = ComplexityLevel.DIRECT
        for threshold, lvl in LEVEL_THRESHOLDS:
            if score >= threshold:
                level = lvl
                break
        if self.strength_offset:
            reasons.append(f"强度旋钮 {self.strength_offset:+.1f} → 调整后 {score}")
        reasons.append(f"阈值定级 {level}")

        return ComplexityVerdict(
            level=level,
            score=round(score, 2),
            scorer=scorer,
            reasons=reasons,
            injection=injection,
            sanitized_input=sanitized,
        )

    @staticmethod
    def _heuristic_score(text: str) -> float:
        """规则启发式打分（模型不可用时的降级，链路永远有产出）。"""

        score = 1.0  # 有实际语义的输入基线
        if len(text) > 80:
            score += 1.0
        score += min(len(_MULTI_TOOL_HINTS.findall(text)) * 0.8, 3.0)
        score += min(len(_TOOL_HINTS.findall(text)) * 0.7, 2.5)
        if _HIGH_RISK_HINTS.search(text):
            score += 1.5  # 高风险词倾向走完整编排（含审批/验证）
        return round(min(score, 10.0), 2)


__all__ = [
    "ComplexityLevel",
    "ComplexityRouter",
    "ComplexityVerdict",
    "CRISIS_RESPONSE",
    "LEVEL_THRESHOLDS",
]

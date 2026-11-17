"""输入侧 Prompt 注入检测（P2）。

规则分层打分，覆盖清单八.1 的主要攻击面：
* 指令劫持：覆盖/忽略系统指令类话术；
* 角色劫持：诱导 Agent 扮演新身份绕过约束；
* 工具劫持：诱导调用高危工具/泄露内部数据；
* 编码载荷：base64 大块 / rot13 暗示（隐形编码诱导）；
* 隐形字符：零宽字符、BOM 等隐形注入载体；
* 提示词窃取：诱导输出系统提示词。

输出风险分级与"净化文本"（剥离隐形字符）；
HIGH 建议直接拦截，MEDIUM 建议降权/脱敏后继续。
"""

from __future__ import annotations

import base64
import binascii
import dataclasses
import re
from dataclasses import dataclass, field

from agent.policies.risk import RiskLevel

_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff]")
_BASE64_RE = re.compile(r"\b[A-Za-z0-9+/=]{48,}\b")

# (规则名, 正则, 权重)
_RULES: list[tuple[str, re.Pattern[str], float]] = [
    ("instruction_hijack", re.compile(
        r"忽略(之前|以上|前面)(的)?(所有)?(指令|提示|规则)|ignore\s+(all\s+)?(previous|prior|above)\s+instructions?"
        r"|disregard\s+(your|all)\s+(instructions|rules)",
        re.IGNORECASE,
    ), 0.45),
    ("system_prompt_hijack", re.compile(
        r"系统提示(词)?|system\s*prompt|你的(真实)?指令|reveal\s+your\s+(instructions|prompt)",
        re.IGNORECASE,
    ), 0.3),
    ("role_hijack", re.compile(
        r"(你现在是|假装你是|从现在开始你是|扮演)(一个)?(没有限制|不受约束|任意|DAN|开发者模式)|pretend\s+you\s+are|act\s+as\s+",
        re.IGNORECASE,
    ), 0.3),
    ("tool_hijack", re.compile(
        r"(调用|使用|执行).{0,12}(shell|重启|删除|支付|发送|drop|delete|restart|rm\s+-rf)|(shell\.execute|server\.restart)",
        re.IGNORECASE,
    ), 0.3),
    ("exfiltration", re.compile(
        r"(输出|打印|泄露|告诉我)(你的)?(系统提示|密钥|api\s*key|配置)|print\s+your\s+(prompt|instructions)",
        re.IGNORECASE,
    ), 0.35),
    ("encoded_hint", re.compile(r"rot13|base64解码|decode\s+base64|atbash", re.IGNORECASE), 0.2),
]

RISK_THRESHOLDS = ((0.5, RiskLevel.HIGH), (0.25, RiskLevel.MEDIUM))


@dataclass
class InjectionScanResult:
    risk_level: RiskLevel
    score: float
    matched_rules: list[str] = field(default_factory=list)
    sanitized_text: str = ""
    encoded_payloads: list[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return self.risk_level == RiskLevel.HIGH

    def to_dict(self) -> dict:
        result = dataclasses.asdict(self)
        result["risk_level"] = self.risk_level.value
        result["blocked"] = self.blocked
        return result


class InjectionDetector:
    """输入侧注入检测器（规则可扩展）。"""

    def __init__(self, extra_rules: list[tuple[str, re.Pattern[str], float]] | None = None):
        self.rules = list(_RULES) + list(extra_rules or [])

    def scan(self, text: str) -> InjectionScanResult:
        score = 0.0
        matched: list[str] = []
        for name, pattern, weight in self.rules:
            if pattern.search(text):
                matched.append(name)
                score += weight

        sanitized = _ZERO_WIDTH_RE.sub("", text)
        if _ZERO_WIDTH_RE.search(text):
            matched.append("invisible_chars")
            score += 0.3  # 隐形字符本身就是强注入信号

        encoded: list[str] = []
        for candidate in _BASE64_RE.findall(sanitized):
            try:
                decoded = base64.b64decode(candidate, validate=True)
                if decoded.isascii() and len(decoded) >= 16:
                    encoded.append(candidate)
                    score += 0.25
                    matched.append("base64_payload")
            except (binascii.Error, ValueError):
                continue

        score = min(score, 1.0)
        risk = RiskLevel.LOW
        for threshold, level in RISK_THRESHOLDS:
            if score >= threshold:
                risk = level
                break

        return InjectionScanResult(
            risk_level=risk,
            score=round(score, 3),
            matched_rules=matched,
            sanitized_text=sanitized,
            encoded_payloads=encoded,
        )


__all__ = [
    "InjectionDetector",
    "InjectionScanResult",
]

"""输入侧注入检测（P2 企业级覆盖矩阵）。

规则分层打分，覆盖六类真实攻击面：
* Prompt 注入：指令劫持 / 角色劫持 / 工具劫持 / 提示词窃取；
* SQL 注入：永真式、注释截断、堆叠语句、UNION 探测、时间盲注；
* 命令注入：命令替换、命令拼接、反弹 shell；
* XSS：脚本标签、事件处理器、javascript: 协议；
* 路径遍历：../ 变体、URL 编码与畸形编码绕过；
* 代码注入：eval / exec / __import__ / system / compile+import；
* 编码与隐形载荷：base64 大块、零宽字符、BOM。

防误杀机制：在学习/防御语境（"什么是""如何防止""这段代码……"）下，
术语型规则降权 50%（记录命中但不直接拦截），结构型攻击规则不降权，
保证"讨论攻击原理"放行、"贴出攻击语法"拦截。
输出风险分级与净化文本；HIGH 直接拦截，MEDIUM 降权/脱敏后继续。
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

# 学习/防御语境标记：命中后仅对术语型规则降权，结构型攻击不享受豁免
_LEARNING_CONTEXT_RE = re.compile(
    r"解释|什么是|怎么|如何|防止|防御|防护|转义|正则|作用是|这段代码|字段表示"
    r"|文档里提到|讨论|建议不要|用途|原理|教学|学习",
    re.IGNORECASE,
)

# (规则名, 正则, 权重)
_RULES: list[tuple[str, re.Pattern[str], float]] = [
    # ---- Prompt 注入 ----
    ("instruction_hijack", re.compile(
        r"忽略(之前|以上|前面)(的)?(所有)?(指令|提示|规则)"
        r"|ignore\s+(all\s+)?(previous|prior|above)\s+instructions?"
        r"|disregard\s+(your|all)\s+(instructions|rules)",
        re.IGNORECASE,
    ), 0.6),
    ("system_prompt_hijack", re.compile(
        r"系统提示词?|system\s*prompt|reveal\s+your\s+(instructions|prompt)"
        r"|your\s+(system\s+)?(prompt|instructions)",
        re.IGNORECASE,
    ), 0.3),
    ("role_hijack", re.compile(
        r"(你现在是|假装你是|从现在开始你是|扮演)(一个)?(没有任何限制|没有限制|毫无限制|不受约束|任意|DAN|开发者模式)"
        r"|pretend\s+you|act\s+as\s+an?\s+(unrestricted|unlimited|jailbroken)"
        r"|you\s+are\s+(now\s+)?an?\s+(unrestricted|unlimited|jailbroken)"
        r"|\bDAN\b|no\s+(limits|restrictions)|do\s+anything\s+i\s+say",
        re.IGNORECASE,
    ), 0.6),
    ("tool_hijack", re.compile(
        r"(调用|使用|执行).{0,12}(shell|重启|删除|支付|发送|drop|delete|restart|rm\s+-rf)|(shell\.execute|server\.restart)",
        re.IGNORECASE,
    ), 0.3),
    ("exfiltration", re.compile(
        r"(输出|打印|泄露|告诉我)(你的)?.{0,8}(系统提示|密钥|api\s*key|配置)"
        r"|print\s+your\s+(system\s+)?(prompt|instructions)"
        r"|output\s+the\s+system\s*prompt",
        re.IGNORECASE,
    ), 0.35),
    ("prompt_probe", re.compile(
        r"what\s+are\s+your\s+(instructions|rules)", re.IGNORECASE
    ), 0.4),
    ("prompt_repeat", re.compile(
        r"repeat\s+the\s+(above|previous)\s+instructions", re.IGNORECASE
    ), 0.55),
    ("encoded_hint", re.compile(r"rot13|base64解码|decode\s+base64|atbash", re.IGNORECASE), 0.2),
    # ---- SQL 注入 ----
    ("sql_tautology", re.compile(
        r"(['\"])\s*(?:or|and)\s+['\"]?(\w+)['\"]?\s*=\s*['\"]?\2['\"]?",
        re.IGNORECASE,
    ), 0.7),
    ("sql_tautology_numeric", re.compile(
        r"(?<![\w.])\d+\s+(?:or|and)\s+\d+\s*=\s*\d+", re.IGNORECASE
    ), 0.7),
    ("sql_comment", re.compile(r"['\"]\s*(?:--|#|/\*)"), 0.6),
    ("sql_stacked", re.compile(
        r";\s*(?:drop|delete|truncate|update|insert)\b", re.IGNORECASE
    ), 0.6),
    ("sql_union_select", re.compile(
        r"\bunion\s+(?:all\s+)?select\b", re.IGNORECASE
    ), 0.6),
    ("sql_time_based", re.compile(
        r"\b(?:sleep|pg_sleep|benchmark)\s*\(|\bwaitfor\s+delay\b", re.IGNORECASE
    ), 0.55),
    # ---- 命令注入 ----
    ("cmd_substitution", re.compile(r"\$\([^)]{1,120}\)|`[^`]{1,120}`"), 0.55),
    ("cmd_chain", re.compile(
        r"(?:;|&&|\|\||\|)\s*(?:rm\s+-rf|cat\s+/etc/|curl\b|wget\b|nc\b|ncat\b|bash\b|sh\b|id\b|whoami)",
        re.IGNORECASE,
    ), 0.6),
    ("reverse_shell", re.compile(
        r"\b(?:nc|ncat)\b[^\n]{0,40}?-e\s+/(?:bin/)?(?:ba)?sh|/dev/tcp/|bash\s+-i",
        re.IGNORECASE,
    ), 0.7),
    # ---- XSS ----
    ("xss_tag", re.compile(
        r"<\s*(?:script|iframe|svg|img)\b[^>]*>|javascript\s*:|on\w+\s*=",
        re.IGNORECASE,
    ), 0.6),
    # ---- 路径遍历 ----
    ("path_traversal", re.compile(r"\.{2,}[\\/]+|%2e%2e|%c0%af", re.IGNORECASE), 0.6),
    # ---- 代码注入 ----
    ("code_injection", re.compile(
        r"\beval\s*\(|__import__\s*\(|\.system\s*\(|\bexec\s*\(|\bcompile\s*\([^)]*import",
        re.IGNORECASE,
    ), 0.55),
]

# 术语型规则：学习/防御语境下降权；结构型攻击规则不在此集合，保持全权重
_SOFT_RULES = {
    "system_prompt_hijack",
    "encoded_hint",
    "sql_union_select",
    "sql_time_based",
    "xss_tag",
}

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
        learning = bool(_LEARNING_CONTEXT_RE.search(text))
        for name, pattern, weight in self.rules:
            if pattern.search(text):
                matched.append(name)
                # 学习/防御语境只对术语型规则降权；结构型攻击语法不受保护
                score += weight * 0.5 if learning and name in _SOFT_RULES else weight

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

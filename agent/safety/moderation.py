"""输出侧审核钩子（P2）。

对 Agent 最终输出做后置审核：
* 内置敏感信息检测：手机号、身份证、API 密钥、私钥块；
* 自动脱敏：掩码替换后返回 redacted_text；
* 可插拔扩展：外部 checker 返回违规 flag 列表即可接入（如接审核模型）。

幻觉抑制的引用标注由 RAG 层负责，本模块只做"事实类有害输出"的兜底过滤。
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from typing import Callable

Checker = Callable[[str], list[str]]

_SENSITIVE_PATTERNS: list[tuple[str, re.Pattern[str], Callable[[re.Match], str]]] = [
    ("phone", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), lambda m: m.group(0)[:3] + "****" + m.group(0)[7:]),
    ("id_card", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), lambda m: m.group(0)[:6] + "********" + m.group(0)[-4:]),
    ("api_key", re.compile(r"\b(sk-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16})\b"), lambda m: m.group(0)[:5] + "***REDACTED***"),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
     lambda m: "-----BEGIN PRIVATE KEY-----***REDACTED***-----END PRIVATE KEY-----"),
]


@dataclass
class ModerationResult:
    allowed: bool
    flags: list[str] = field(default_factory=list)
    redacted_text: str = ""
    redacted: bool = False

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


class OutputModerator:
    """输出审核器：内置脱敏 + 可插拔 checker。"""

    def __init__(self, checkers: list[Checker] | None = None):
        self.checkers = list(checkers or [])

    def moderate(self, text: str) -> ModerationResult:
        flags: list[str] = []
        redacted = text

        for name, pattern, mask in _SENSITIVE_PATTERNS:
            if pattern.search(redacted):
                flags.append(name)
                redacted = pattern.sub(mask, redacted)

        for checker in self.checkers:
            try:
                flags.extend(checker(text))
            except Exception:
                # 外部审核器故障不能阻断正常输出，只能记录 flag
                flags.append("checker_error")

        # checker 可声明硬拦截 flag：以 block: 前缀开头
        blocked = any(flag.startswith("block:") for flag in flags)
        return ModerationResult(
            allowed=not blocked,
            flags=flags,
            redacted_text=redacted,
            redacted=redacted != text,
        )


__all__ = [
    "ModerationResult",
    "OutputModerator",
]

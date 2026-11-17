"""护栏判定契约：唯一的跨层返回类型。

action 语义（DESIGN §5）：
- ALLOW   放行，正常链路
- BLOCK   拒绝（输入不进模型；输出整段替换为拒绝话术）
- REDACT  脱敏后继续（redacted 携带脱敏后的文本）
- FILTER  仅剔除命中片段（RAG citations 场景），其余保留
"""

from dataclasses import dataclass, field

ACTION_ALLOW = "ALLOW"
ACTION_BLOCK = "BLOCK"
ACTION_REDACT = "REDACT"
ACTION_FILTER = "FILTER"

_PASSED = {ACTION_ALLOW, ACTION_REDACT, ACTION_FILTER}


@dataclass(frozen=True)
class GuardDecision:
    action: str
    reasons: tuple[str, ...] = ()
    redacted: str | None = None
    filtered_citations: tuple | None = None
    rule_version: str = "1.0.0"

    @property
    def passed(self) -> bool:
        """BLOCK 视为未通过；ALLOW/REDACT/FILTER 均可在处置后继续。"""
        return self.action in _PASSED

    def with_version(self, rule_version: str) -> "GuardDecision":
        if self.rule_version == rule_version:
            return self
        return GuardDecision(
            action=self.action,
            reasons=self.reasons,
            redacted=self.redacted,
            filtered_citations=self.filtered_citations,
            rule_version=rule_version,
        )


ALLOW = GuardDecision(action=ACTION_ALLOW)

"""输出侧护栏：answer 返回给用户前的确定性检查。

检查顺序（DESIGN §4⑤）：越权承诺（REDACT）→ PII 泄露（REDACT）→
兜底控制符。全部未命中返回 ALLOW。
"""

import logging

from .contract import ALLOW, ACTION_REDACT, GuardDecision
from .input_guard import ensure_safe
from .rules import INVISIBLE_CTRL, OUTPUT_RULES, PII_RULES, REDACT_PLACEHOLDER

logger = logging.getLogger(__name__)


def check_output(answer: str) -> GuardDecision:
    """对模型完整输出做检查。REDACT 携带脱敏后的全文。"""
    if not isinstance(answer, str) or not answer:
        return ALLOW

    redacted = answer
    hits: list[str] = []

    for rule in OUTPUT_RULES:
        if rule.pattern.search(redacted):
            redacted = rule.pattern.sub(
                "[该操作未经工具确认，不能声称已执行]", redacted
            )
            hits.append(rule.id)

    for rule in PII_RULES:
        if rule.pattern.search(redacted):
            redacted = rule.pattern.sub(REDACT_PLACEHOLDER, redacted)
            hits.append(rule.id)

    if hits:
        logger.info("guard.output redacted=%s", ",".join(hits))
        return GuardDecision(action=ACTION_REDACT, reasons=tuple(hits), redacted=redacted)

    if INVISIBLE_CTRL.search(answer):
        return GuardDecision(action=ACTION_REDACT, reasons=("CTL_CHARS",), redacted=answer)

    return ALLOW


def check_output_safe(answer: str, *, fail_closed: bool) -> GuardDecision:
    """fail-closed 包装版，供 chat 链路调用（异常时按配置拒绝）。"""
    return ensure_safe(check_output, answer, fail_closed=fail_closed)

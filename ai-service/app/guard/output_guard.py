"""输出侧护栏：answer 返回给用户前的确定性检查。

检查顺序（DESIGN §4⑤）：越权承诺（REDACT）→ PII 泄露（REDACT）→
兜底控制符。全部未命中返回 ALLOW。
"""

import logging
import re

from .contract import ACTION_BLOCK, ALLOW, ACTION_REDACT, GuardDecision
from .input_guard import ensure_safe
from .rules import INVISIBLE_CTRL, OUTPUT_RULES, PII_RULES, REDACT_PLACEHOLDER

logger = logging.getLogger(__name__)

# 证据引用统一形如 ev-xxxx，与 EvidenceRef.evidence_id 同规则。
EVIDENCE_REF = re.compile(r"ev-[A-Za-z0-9_\-]+")


def check_output(answer: str, allowed_refs=None) -> GuardDecision:
    """对模型完整输出做检查。REDACT 携带脱敏后的全文。

    allowed_refs 非 None 时叠加 RATIONALE_CITES_UNKNOWN_REF：模型输出里引用了
    封套外 evidence_id 即幻觉，BLOCK 优先合并；为 None 时不调用该规则，
    与旧版逐字节等价（生产 chat 暂无证据封套，走此分支）。
    """
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
        base = GuardDecision(action=ACTION_REDACT, reasons=tuple(hits), redacted=redacted)
    elif INVISIBLE_CTRL.search(answer):
        base = GuardDecision(action=ACTION_REDACT, reasons=("CTL_CHARS",), redacted=answer)
    else:
        base = ALLOW

    if allowed_refs is None:
        return base
    return _merge_block_priority(base, check_decision_citations(answer, allowed_refs))


def check_output_safe(answer: str, *, fail_closed: bool, allowed_refs=None) -> GuardDecision:
    """fail-closed 包装版，供 chat 链路调用（异常时按配置拒绝）。

    allowed_refs 透传给 check_output：None 时与旧版逐字节等价。
    """
    return ensure_safe(
        check_output, answer, fail_closed=fail_closed, allowed_refs=allowed_refs
    )


def _merge_block_priority(base: GuardDecision, cite: GuardDecision) -> GuardDecision:
    """BLOCK 优先合并：cite（幻觉判定）或 base 任一为 BLOCK 即返回 BLOCK，
    cite 的 BLOCK 优先（更具体的确定性拒绝）；否则保留 base 的 action/redacted，
    reasons 合并去重保序（cite 为 ALLOW 时 reasons 为空，直接返回 base）。
    """
    if cite.action == ACTION_BLOCK:
        return cite
    if base.action == ACTION_BLOCK:
        return base
    if not cite.reasons:
        return base
    merged = tuple(dict.fromkeys(base.reasons + cite.reasons))
    return GuardDecision(action=base.action, reasons=merged, redacted=base.redacted)


def check_decision_citations(answer: str, allowed_refs) -> GuardDecision:
    """RATIONALE_CITES_UNKNOWN_REF：判定输出引用了封套外证据 id = 幻觉。

    allowed_refs 应为「输入封套 refs[].evidence_id ∪ 输出 used_refs」，调用方负责并集，
    本函数只做确定性比对，不猜意图。
    """
    if not isinstance(answer, str) or not answer:
        return ALLOW

    unknown = sorted(set(EVIDENCE_REF.findall(answer)) - set(allowed_refs))
    if unknown:
        logger.info(
            "guard.output rule=RATIONALE_CITES_UNKNOWN_REF unknown=%s", ",".join(unknown)
        )
        return GuardDecision(
            action=ACTION_BLOCK, reasons=("RATIONALE_CITES_UNKNOWN_REF",)
        )
    return ALLOW

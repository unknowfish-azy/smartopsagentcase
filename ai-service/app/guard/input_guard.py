"""输入侧护栏：用户消息 + RAG citations 的确定性检查。

入口契约（DESIGN §4②/W2）：
- check_input(message)    -> GuardDecision（BLOCK / REDACT / ALLOW）
- check_citations(items)  -> GuardDecision（FILTER / ALLOW）
- ensure_safe(message)    -> fail-closed 包装：护栏自身异常按配置拒绝
"""

import base64
import binascii
import logging
import urllib.parse

from .contract import ALLOW, ACTION_BLOCK, ACTION_REDACT, GuardDecision
from .rules import (
    INJECTION_RULES,
    INVISIBLE_CTRL,
    PII_RULES,
    REDACT_PLACEHOLDER,
    ZERO_WIDTH,
)

logger = logging.getLogger(__name__)


def _decode_variants(text: str) -> list[str]:
    """生成原文与各解码变体，编码绕过在变体上仍会命中规则。

    覆盖：零宽/控制符剔除、base64、hex、URL 编码。解码失败静默跳过
    （不是每个字符串都是合法编码）。
    """
    variants = [text]
    cleaned = ZERO_WIDTH.sub("", INVISIBLE_CTRL.sub("", text))
    if cleaned != text:
        variants.append(cleaned)
    for candidate in (text.strip(), cleaned.strip()):
        for decoder in (base64.b64decode, binascii.unhexlify, urllib.parse.unquote):
            try:
                decoded = decoder(candidate)
            except Exception:
                continue
            # b64/hex 返回 bytes，unquote 返回 str——统一成文本。
            if isinstance(decoded, bytes):
                decoded = decoded.decode("utf-8", "ignore")
            if decoded and decoded not in variants:
                variants.append(decoded)
    return variants


def check_input(message: str) -> GuardDecision:
    """对用户消息做输入侧检查。

    顺序：先全变体扫注入（BLOCK 短路），再 PII 脱敏（REDACT），
    最后不可见控制符兜底（BLOCK）。
    """
    if not isinstance(message, str) or not message:
        return ALLOW

    for variant in _decode_variants(message):
        for rule in INJECTION_RULES:
            if rule.pattern.search(variant):
                return GuardDecision(
                    action=ACTION_BLOCK,
                    reasons=(rule.id,),
                )

    redacted = message
    hits: list[str] = []
    for rule in PII_RULES:
        if rule.pattern.search(redacted):
            redacted = rule.pattern.sub(REDACT_PLACEHOLDER, redacted)
            hits.append(rule.id)
    if hits:
        return GuardDecision(
            action=ACTION_REDACT,
            reasons=tuple(hits),
            redacted=redacted,
        )

    if INVISIBLE_CTRL.search(message):
        return GuardDecision(
            action=ACTION_BLOCK,
            reasons=("CTL_CHARS",),
        )

    return ALLOW


def check_citations(items: list) -> GuardDecision:
    """RAG 证据进入 prompt 前的脏文档过滤（DESIGN §4②）。

    只剔除命中片段，干净片段原样保留（保序）；全部剔除时调用方
    按空证据分支处理（项目已有 retrieval_status=empty 语义）。
    items 是 dict 列表：results 用 content 字段（进 prompt），
    citations 用 snippet 字段（前端展示），两者都支持。
    """
    if not items:
        return ALLOW

    kept: list = []
    dropped = 0
    for item in items:
        if isinstance(item, dict):
            text = str(item.get("content", "") or item.get("snippet", ""))
        else:
            text = str(getattr(item, "content", "") or getattr(item, "snippet", ""))
        dirty = any(rule.pattern.search(text) for rule in PII_RULES) or any(
            rule.pattern.search(text) for rule in INJECTION_RULES
        )
        if dirty:
            dropped += 1
        else:
            kept.append(item)

    if dropped:
        logger.info("guard.citations filtered=%s kept=%s", dropped, len(kept))
        return GuardDecision(
            action="FILTER",
            reasons=("RAG_DIRTY",),
            filtered_citations=tuple(kept),
        )
    return ALLOW


def ensure_safe(check, message: str, *, fail_closed: bool, **kwargs) -> GuardDecision:
    """fail-closed 包装：护栏自身抛异常时按配置拒绝，绝不静默放行。

    fail_closed=True 返回 BLOCK（reasons=GUARD_ERROR）；
    fail_closed=False 放行并记录异常——两条路都留痕，不存在第三种。
    **kwargs 透传给被包装函数（如 check_output 的 allowed_refs），不传时行为不变。
    """
    try:
        return check(message, **kwargs)
    except Exception as exc:  # noqa: BLE001 - 护栏不得向业务链路抛异常
        logger.exception("guard.error fail_closed=%s", fail_closed)
        if fail_closed:
            return GuardDecision(action=ACTION_BLOCK, reasons=("GUARD_ERROR",))
        _ = exc
        return ALLOW

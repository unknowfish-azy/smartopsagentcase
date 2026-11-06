"""PERF-07：上下文预算、按复杂度路由模型与检索缓存。

三件事的边界必须说清楚，不许把"机制存在"说成"效果已验证"：

1. **上下文预算**（``ContextBudget``）——把 RAG 证据按分数优先装进字符预算，
   超预算时先丢弃低分证据、再截断单条内容，并如实返回"保留了什么、丢了什么"。
2. **模型路由**（``ModelRouter``）——按请求复杂度选模型；未配置路由模型时
   如实回落到全局模型并标注 ``routing_disabled``，绝不假装"已路由"。
3. **检索缓存**（``RagQueryCache``）——避免重复检索。缓存键包含
   租户、权限（用户与角色）、知识版本与全部检索参数：任何一项不同都不共享。
   进程内 TTL + 条目上限，超限淘汰最旧条目。

"用同一故障集比较正确率、假成功率、token、首响应及总耗时"属于验收实验，
需要真实 LLM 与故障集数据，不在本模块范围内——本模块只提供可被该实验
度量的机制，并在响应元数据里暴露预算/路由/缓存的真实决策。
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# 1. 上下文预算
# ---------------------------------------------------------------------------

_DEFAULT_BUDGET_CHARS = 12000
_DEFAULT_PER_ITEM_CHARS = 4000


@dataclass(frozen=True)
class BudgetStats:
    """一次预算裁剪的如实账目。"""

    budget_chars: int
    used_chars: int
    kept: int
    dropped: int
    truncated_items: int


class ContextBudget:
    """证据字符预算器。

    规则（顺序固定，保证可复现）：
    - 按 score 降序稳定排序（同分保持原顺序）；
    - 高分证据优先装入预算，装不下的整条丢弃（dropped）；
    - 能装下但超单条上限的截断内容（truncated）；
    - 至少保留一条证据（哪怕截断到很短），避免"有证据但一条都不给"。
    """

    def __init__(
        self,
        budget_chars: int = _DEFAULT_BUDGET_CHARS,
        per_item_chars: int = _DEFAULT_PER_ITEM_CHARS,
    ) -> None:
        self.budget_chars = max(500, budget_chars)
        self.per_item_chars = max(200, per_item_chars)

    def apply(self, results: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], BudgetStats]:
        if not results:
            return [], BudgetStats(0, 0, 0, 0, 0)

        ordered = sorted(
            enumerate(results),
            key=lambda pair: (-float(pair[1].get("score", 0.0)), pair[0]),
        )

        budgeted: list[dict[str, Any]] = []
        used = 0
        dropped = 0
        truncated = 0

        for _, item in ordered:
            content = str(item.get("content", ""))
            if not budgeted:
                # 至少保一条：即使超预算也截断保留，不让上下文凭空变空
                capped = content[: self.per_item_chars]
                if len(capped) < len(content):
                    truncated += 1
                budgeted.append({**item, "content": capped})
                used = len(capped)
                continue
            if used + len(content) > self.budget_chars:
                dropped += 1
                continue
            if len(content) > self.per_item_chars:
                capped = content[: self.per_item_chars]
                truncated += 1
                budgeted.append({**item, "content": capped})
                used += len(capped)
            else:
                budgeted.append({**item})
                used += len(content)

        stats = BudgetStats(
            budget_chars=self.budget_chars,
            used_chars=used,
            kept=len(budgeted),
            dropped=dropped,
            truncated_items=truncated,
        )
        return budgeted, stats

    def stats_dict(self, stats: BudgetStats) -> dict[str, int]:
        return {
            "budget_chars": stats.budget_chars,
            "used_chars": stats.used_chars,
            "kept": stats.kept,
            "dropped": stats.dropped,
            "truncated_items": stats.truncated_items,
        }


# ---------------------------------------------------------------------------
# 2. 按复杂度路由模型
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RoutingDecision:
    """一次模型路由的决策记录（进响应元数据，可审计）。"""

    complexity: str
    model: str
    routed: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)


class ModelRouter:
    """按请求复杂度选择模型。

    复杂度信号（任一命中即 complex）：
    - 携带图像证据；
    - 消息长度超过阈值（默认 400 字）；
    - 检索证据条数多（默认 > 8）；
    - 请求要求核验（verification_required）。

    未配置 simple/complex 模型（留空）时如实返回 ``routed=False``，
    模型沿用全局配置——而不是悄悄拿同一个模型冒充"已路由"。
    """

    def __init__(
        self,
        default_model: str,
        simple_model: str = "",
        complex_model: str = "",
        message_threshold: int = 400,
        evidence_threshold: int = 8,
    ) -> None:
        self.default_model = default_model
        self.simple_model = simple_model.strip()
        self.complex_model = complex_model.strip()
        self.message_threshold = message_threshold
        self.evidence_threshold = evidence_threshold

    @property
    def enabled(self) -> bool:
        return bool(self.simple_model or self.complex_model)

    def route(
        self,
        message: str,
        *,
        images: list[str] | None = None,
        evidence_count: int = 0,
        verification_required: bool = False,
    ) -> RoutingDecision:
        reasons: list[str] = []
        if images:
            reasons.append("images")
        if len(message) > self.message_threshold:
            reasons.append(f"message>{self.message_threshold}")
        if evidence_count > self.evidence_threshold:
            reasons.append(f"evidence>{self.evidence_threshold}")
        if verification_required:
            reasons.append("verification_required")

        complexity = "complex" if reasons else "simple"

        if not self.enabled:
            return RoutingDecision(
                complexity=complexity,
                model=self.default_model,
                routed=False,
                reasons=tuple(reasons) or ("default",),
            )

        if complexity == "complex":
            model = self.complex_model or self.default_model
        else:
            model = self.simple_model or self.default_model
        return RoutingDecision(
            complexity=complexity,
            model=model,
            routed=model != self.default_model,
            reasons=tuple(reasons) or ("no_complexity_signal",),
        )

    def decision_dict(self, decision: RoutingDecision) -> dict[str, Any]:
        return {
            "complexity": decision.complexity,
            "model": decision.model,
            "routed": decision.routed,
            "reasons": list(decision.reasons),
        }


# ---------------------------------------------------------------------------
# 3. 检索缓存（避免重复查询）
# ---------------------------------------------------------------------------

_DEFAULT_TTL_SEC = 60
_DEFAULT_MAX_ENTRIES = 128


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    puts: int = 0
    evictions: int = 0


class RagQueryCache:
    """进程内 RAG 检索缓存。

    缓存键（SHA-256）包含：租户、用户、角色（权限）、知识版本、查询文本
    与全部检索参数。任何一项不同都是不同的键——防止跨租户/跨权限串结果。

    只有检索**成功**的结果才进缓存；降级/失败结果绝不缓存，
    避免把一次故障的空结果固化成"知识库没有"。
    """

    def __init__(
        self,
        ttl_sec: float = _DEFAULT_TTL_SEC,
        max_entries: int = _DEFAULT_MAX_ENTRIES,
        clock: Any = time.monotonic,
    ) -> None:
        self.ttl_sec = max(0.0, ttl_sec)
        self.max_entries = max(1, max_entries)
        self._clock = clock
        self._store: dict[str, tuple[float, dict[str, Any]]] = {}
        self.stats = CacheStats()

    @staticmethod
    def make_key(
        query: str,
        *,
        tenant: str,
        user: str,
        role: str,
        version: str | None,
        top_k: int,
        source: str | None,
        score_threshold: float | None,
        vector_weight: float | None,
        bm25_weight: float | None,
    ) -> str:
        material = json.dumps(
            {
                "query": query,
                "tenant": tenant,
                "user": user,
                "role": role,
                "version": version or "",
                "top_k": top_k,
                "source": source or "",
                "score_threshold": score_threshold,
                "vector_weight": vector_weight,
                "bm25_weight": bm25_weight,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def get(self, key: str) -> dict[str, Any] | None:
        entry = self._store.get(key)
        if entry is None:
            self.stats.misses += 1
            return None
        stored_at, value = entry
        if self._clock() - stored_at > self.ttl_sec:
            del self._store[key]
            self.stats.misses += 1
            return None
        self.stats.hits += 1
        return value

    def put(self, key: str, value: dict[str, Any]) -> None:
        # 降级/失败结果不缓存：一次上游故障不应被固化为"没有知识"。
        if value.get("degraded"):
            return
        if value.get("retrieval_status") == "failed":
            return
        self._store[key] = (self._clock(), value)
        self.stats.puts += 1
        while len(self._store) > self.max_entries:
            oldest = min(self._store, key=lambda k: self._store[k][0])
            del self._store[oldest]
            self.stats.evictions += 1

    def stats_dict(self) -> dict[str, int]:
        return {
            "hits": self.stats.hits,
            "misses": self.stats.misses,
            "entries": len(self._store),
            "evictions": self.stats.evictions,
        }

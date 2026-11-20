"""Transformer 启发的证据重排：双头注意力 + 去冗余。

这里的「双头」不是神经网络，而是两个确定性的打分视角：

- **语义头**：沿用知识服务返回的检索分数（向量 + BM25 混合结果）；
- **词项头**：问题关键实体/动作在证据正文中的覆盖比例。

两路加权后再做一次相似度去冗余（近似 MMR），避免高相似的重复证据
挤占上下文预算。所有计算可复现：不引入随机数，不额外调用模型。

设计边界：本模块只重排「已经检索到的证据」，不负责发起检索，
也不改变知识服务的返回契约；调用方据此决定是否进 prompt。
"""

from __future__ import annotations

import re
from typing import Any, Iterable

_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_WORD_RE = re.compile(r"[A-Za-z0-9_.+\-]+")

# 只保留高频虚词与客套词，避免把「怎么/如何」这类真正的运维问法过滤掉。
_STOPWORDS = frozenset(
    {
        "帮我", "请帮", "一下", "请问", "告诉", "介绍", "说说", "看看",
        "我们", "你们", "他们", "这个", "那个", "这些", "那些", "以及",
        "然后", "而且", "但是", "因为", "所以", "如果", "可以", "需要",
        "the", "and", "for", "with", "that", "this", "from", "what", "how",
    }
)

_DEFAULT_SIMILARITY_THRESHOLD = 0.86


def query_terms(text: str | None, limit: int = 32) -> list[str]:
    """把问题切成可匹配的词项：中文 bigram + 英文/数字整词。

    顺序按出现先后保留，重复项只留一次；短于 2 字的中文串不参与匹配，
    避免单字造成大面积误命中。
    """
    terms: list[str] = []
    seen: set[str] = set()

    for chunk in _CJK_RE.findall(text or ""):
        if len(chunk) < 2:
            continue
        for index in range(len(chunk) - 1):
            term = chunk[index:index + 2]
            if term in _STOPWORDS or term in seen:
                continue
            seen.add(term)
            terms.append(term)

    for word in _WORD_RE.findall(text or ""):
        term = word.lower()
        if len(term) < 2 or term in _STOPWORDS or term in seen:
            continue
        seen.add(term)
        terms.append(term)

    return terms[:limit]


def _bigrams(text: str) -> set[str]:
    """字符 bigram 集合，用于粗略相似度（去重与冗余判断）。"""
    normalized = re.sub(r"\s+", "", text or "")
    if len(normalized) < 2:
        return {normalized} if normalized else set()
    return {normalized[i:i + 2] for i in range(len(normalized) - 1)}


def similarity(left: str, right: str) -> float:
    """Jaccard 相似度，取值范围 0~1。"""
    a = _bigrams(left)
    b = _bigrams(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def attention_rerank(
    results: Iterable[dict[str, Any]],
    query: str | None,
    *,
    semantic_weight: float = 0.65,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """语义分与词项覆盖度加权排序。

    语义分按本次候选集的最大值归一化，避免不同知识服务分数量纲不一致；
    词项覆盖度 = 命中的问题词项数 / 问题词项总数。
    返回 (排序后的证据, 统计信息)，统计信息用于响应元数据审计。
    """
    items = list(results or [])
    terms = query_terms(query)
    meta: dict[str, Any] = {
        "terms": len(terms),
        "candidates": len(items),
        "avg_coverage": 0.0,
        "reranked": False,
    }
    if not items:
        return [], meta

    raw_scores = [max(0.0, float(item.get("score", 0.0) or 0.0)) for item in items]
    max_score = max(raw_scores) or 1.0
    weight = min(1.0, max(0.0, semantic_weight))

    scored: list[tuple[float, int, dict[str, Any]]] = []
    total_coverage = 0.0
    for index, item in enumerate(items):
        content = str(item.get("content", "")).lower()
        if terms:
            matched = sum(1 for term in terms if term in content)
            coverage = matched / len(terms)
        else:
            coverage = 0.0
        total_coverage += coverage
        semantic = raw_scores[index] / max_score
        final = weight * semantic + (1.0 - weight) * coverage
        scored.append((final, index, {**item, "attention_score": round(final, 6)}))

    # 同分保持原始顺序，保证结果可复现。
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    meta["avg_coverage"] = round(total_coverage / len(items), 4)
    meta["reranked"] = terms != []
    return [item for _, _, item in scored], meta


def dedupe_similar(
    results: Iterable[dict[str, Any]],
    *,
    threshold: float = _DEFAULT_SIMILARITY_THRESHOLD,
) -> tuple[list[dict[str, Any]], int]:
    """按相似度剔除近似重复证据，保留排序靠前的一条。

    实现是贪心：逐条与已保留证据比较，最大相似度超过阈值就丢弃。
    复杂度 O(n²)，但候选集通常不超过 20 条，开销可忽略。
    """
    kept: list[dict[str, Any]] = []
    dropped = 0
    for item in results or []:
        content = str(item.get("content", ""))
        if any(similarity(content, str(other.get("content", ""))) >= threshold for other in kept):
            dropped += 1
            continue
        kept.append(item)
    return kept, dropped


def rerank_results(
    results: Iterable[dict[str, Any]],
    query: str | None,
    *,
    threshold: float = _DEFAULT_SIMILARITY_THRESHOLD,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """一站式入口：双头加权排序 → 相似度去冗余。"""
    ranked, meta = attention_rerank(results, query)
    kept, dropped = dedupe_similar(ranked, threshold=threshold)
    meta = {**meta, "dropped_duplicates": dropped, "kept": len(kept)}
    return kept, meta

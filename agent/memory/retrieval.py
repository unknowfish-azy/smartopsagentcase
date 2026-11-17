"""记忆混合检索（P2）：关键词 + 向量，双语种分词。

* 关键词得分：英文按词元、中文按单字+二元组重叠（Jaccard），零外部依赖；
* 向量得分：注入任意 Embedder（text -> list[float]）后按余弦相似度；
* 两者加权融合。未注入 Embedder 时退化为纯关键词检索。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Protocol

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


class Embedder(Protocol):
    """向量接口：文本 -> 归一化无关的浮点向量。"""

    def __call__(self, text: str) -> list[float]: ...


def tokenize(text: str) -> set[str]:
    """中英混合分词：英文词元 + 中文单字与二元组。"""

    tokens: set[str] = set()
    for word in _TOKEN_RE.findall(text.lower()):
        tokens.add(word)
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    for ch in cjk:
        tokens.add(ch)
    for i in range(len(cjk) - 1):
        tokens.add(cjk[i] + cjk[i + 1])
    return tokens


def keyword_score(query: str, text: str) -> float:
    q, t = tokenize(query), tokenize(text)
    if not q or not t:
        return 0.0
    return len(q & t) / len(q | t)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


@dataclass
class RetrievalHit:
    key: str
    score: float
    keyword_score: float
    vector_score: float


class HybridRetriever:
    """混合检索器：keyword + vector 加权融合。"""

    def __init__(
        self,
        embedder: Embedder | None = None,
        keyword_weight: float = 0.6,
        vector_weight: float = 0.4,
    ) -> None:
        self.embedder = embedder
        self.keyword_weight = keyword_weight
        self.vector_weight = 0.0 if embedder is None else vector_weight
        if embedder is not None:
            total = self.keyword_weight + self.vector_weight
            self.keyword_weight /= total
            self.vector_weight /= total

    def search(
        self,
        query: str,
        candidates: list[tuple[str, str]],  # (key, text)
        top_k: int = 5,
    ) -> list[RetrievalHit]:
        query_vec = self.embedder(query) if self.embedder else None
        hits: list[RetrievalHit] = []
        for key, text in candidates:
            kw = keyword_score(query, text)
            vec = 0.0
            if query_vec is not None:
                vec = cosine_similarity(query_vec, self.embedder(text))
            score = self.keyword_weight * kw + self.vector_weight * vec
            hits.append(RetrievalHit(key=key, score=score, keyword_score=kw, vector_score=vec))
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:top_k]


__all__ = [
    "Embedder",
    "HybridRetriever",
    "RetrievalHit",
    "cosine_similarity",
    "keyword_score",
    "tokenize",
]

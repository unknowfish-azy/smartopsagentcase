"""双头注意力重排的单元测试。"""

from app.core.attention import (
    dedupe_similar,
    query_terms,
    rerank_results,
    similarity,
)


def test_query_terms_extracts_bigrams_and_words():
    terms = query_terms("请帮我检查 Transformer 的多头注意力是否正常")
    assert "检查" in terms
    assert "attention" not in terms
    assert "transformer" in terms
    assert "帮我" not in terms


def test_attention_rerank_prefers_term_coverage():
    results = [
        {"content": "机房温度与湿度巡检规范", "score": 0.9},
        {"content": "机器人电量低于 30% 时应返航充电", "score": 0.6},
    ]
    ranked, meta = rerank_results(results, "机器人电量低怎么办")
    assert ranked[0]["content"].startswith("机器人电量")
    assert ranked[0]["attention_score"] > ranked[1]["attention_score"]
    assert meta["reranked"] is True
    assert meta["dropped_duplicates"] == 0


def test_attention_rerank_keeps_semantic_order_without_terms():
    results = [{"content": "A", "score": 0.2}, {"content": "B", "score": 0.8}]
    ranked, meta = rerank_results(results, "")
    assert [item["content"] for item in ranked] == ["B", "A"]
    assert meta["reranked"] is False


def test_dedupe_drops_near_duplicate_evidence():
    base = "机器人巡检任务失败时应先急停再检查路线规划与障碍距离"
    results = [
        {"content": base, "score": 0.9},
        {"content": base + "，确认无误后再恢复任务", "score": 0.85},
        {"content": "消防通道占用需要通知安保并留存照片", "score": 0.7},
    ]
    assert similarity(results[0]["content"], results[1]["content"]) > 0.6
    kept, dropped = dedupe_similar(results, threshold=0.55)
    assert dropped == 1
    assert len(kept) == 2


def test_rerank_handles_empty_results():
    ranked, meta = rerank_results([], "任意问题")
    assert ranked == []
    assert meta["candidates"] == 0

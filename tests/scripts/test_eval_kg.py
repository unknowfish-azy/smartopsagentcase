"""EXP-KG-001 评测脚本守卫测试（P2-7 / B5）。

自包含导入：按文件路径加载，绕开 `scripts` 命名空间包解析顺序问题
（同 tests/scripts/test_stats_inference.py 的约定）。

钉住三件事：
1. 指标计算正确（ratio / Wilson、hit / recall / precision）；
2. 金标确实由图派生，且报告**必须**带循环警示（防止把同源结果写成性能证据）；
3. 抽样核对的判据实现与抽取器口径一致（症状字段优先，空则回落标题）。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_MODULE_PATH = REPO / "scripts" / "eval_kg.py"

_spec = importlib.util.spec_from_file_location("eval_kg", _MODULE_PATH)
assert _spec and _spec.loader
kg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kg)


# ============================================================ 指标计算
def test_ratio_matches_wilson_reference():
    ratio = kg._ratio(7, 24)
    assert ratio["num"] == 7 and ratio["den"] == 24
    assert ratio["value"] == pytest.approx(7 / 24, abs=1e-6)
    assert ratio.get("status") is None      # 有分母时不落 NOT_RUN
    lo, hi = ratio["wilson95"]
    assert 0.0 <= lo <= ratio["value"] <= hi <= 1.0


def test_ratio_zero_denominator_is_not_run():
    ratio = kg._ratio(0, 0)
    assert ratio["value"] is None
    assert ratio["status"] == "NOT_RUN"


def test_score_counts_hits_and_recall():
    gold = {"A", "B", "C"}
    scored = kg._score(["A", "X", "Y"], gold)
    assert scored["n_hit"] == 1
    assert scored["hit"] is True
    assert scored["recall"] == pytest.approx(1 / 3)
    assert scored["precision"] == pytest.approx(1 / 3)


def test_score_empty_gold_is_not_a_hit():
    scored = kg._score(["A"], set())
    assert scored["hit"] is False
    assert scored["recall"] is None


# ============================================================ 金标派生
def _entries():
    return [
        {"id": "INC-A", "title": "磁盘只读", "service": "svc1",
         "content": json.dumps({"symptoms": ["磁盘空间耗尽"]}, ensure_ascii=False)},
        {"id": "INC-B", "title": "磁盘清理", "service": "svc1",
         "content": json.dumps({"symptoms": ["磁盘 inode 不足"]}, ensure_ascii=False)},
        {"id": "INC-C", "title": "内存 OOM", "service": "svc2",
         "content": json.dumps({"symptoms": ["内存耗尽"]}, ensure_ascii=False)},
    ]


def test_gold_map_groups_by_shared_root_and_cites():
    entries = _entries()
    extractor = kg.RuleExtractor()
    graph = kg.KnowledgeGraph.from_extraction(extractor.extract_catalog(entries))
    gold = kg.gold_map(entries, extractor, graph)

    assert "INC-B" in gold["INC-A"]        # 同 caused_by 根因（磁盘）
    assert "INC-C" not in gold["INC-A"]    # 根因不同（内存）
    assert "INC-A" not in gold["INC-A"]    # 排除自身


def test_gold_map_includes_cites_targets():
    entries = _entries()
    entries[0]["content"] = json.dumps(
        {"symptoms": ["磁盘空间耗尽"], "relatedIds": ["INC-C"]}, ensure_ascii=False
    )
    extractor = kg.RuleExtractor()
    graph = kg.KnowledgeGraph.from_extraction(extractor.extract_catalog(entries))
    gold = kg.gold_map(entries, extractor, graph)
    assert "INC-C" in gold["INC-A"]


# ============================================================ 辅助函数
def test_result_to_entry_only_accepts_known_ids():
    entries = {"INC-A": {"id": "INC-A"}}
    assert kg.result_to_entry("INC-A", entries) == "INC-A"
    assert kg.result_to_entry("unknown", entries) is None


def test_entry_query_text_falls_back_to_title():
    entry = {"id": "INC-X", "title": "证书过期"}
    assert "证书过期" in kg.entry_query_text(entry)


# ============================================================ 报告口径
def test_markdown_carries_circularity_warning():
    """报告必须显式警示「金标与 KG 同源」，防止误读为性能证据。"""

    entries = _entries()
    extractor = kg.RuleExtractor()
    result = extractor.extract_catalog(entries)
    graph = kg.KnowledgeGraph.from_extraction(result)
    summary = kg.extraction_summary(entries, extractor, graph)
    summary["n_queries"] = 0
    summary["top_k"] = 5
    summary["gold_definition"] = "图派生金标（测试）"
    for arm in ("hybrid", "kg", "hybrid_kg"):
        summary[arm] = {
            "hit_rate": kg._ratio(0, 8),
            "mean_recall": None,
            "mean_gold_size": None,
        }
    summary["complementarity"] = {
        "both_hit": 0, "only_hybrid_hit": 0, "only_kg_hit": 0,
        "neither": 0, "mean_overlap": None,
    }
    audit = {"sample_size": 24, "population": 1, "seed": 1, "value": 1.0,
             "num": 24, "den": 24, "wilson95": [0.0, 1.0], "caveat": "c"}
    rejected_audit = dict(audit)

    text = kg.render_markdown(summary, audit, rejected_audit, "test")
    assert "循环" in text
    assert "不构成" in text
    assert "HashEmbedding" in text

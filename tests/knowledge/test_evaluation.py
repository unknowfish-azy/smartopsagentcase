"""评测链路与向量后端工厂的单元测试。"""

from knowledge.config import KnowledgeConfig
from knowledge.embedding.factory import create_embedding
from knowledge.evaluation.dataset import load_dataset
from knowledge.evaluation.metrics import ndcg_at_k
from knowledge.evaluation.runner import _predicted


def test_factory_defaults_to_hash():
    embedding = create_embedding("hash")
    # RAG-P1-01：工厂返回 EmbeddingModelWithStatus 包装器
    assert embedding.backend_status.backend_requested == "hash"
    assert embedding.backend_status.backend_actual == "hash"


def test_factory_falls_back_when_backend_unknown():
    # 未知后端名不应抛出异常，直接回退哈希词袋，保证服务可启动。
    embedding = create_embedding("not-a-backend")
    assert embedding.backend_status.backend_requested == "not-a-backend"
    assert embedding.backend_status.backend_actual == "hash"
    assert embedding.backend_status.has_fallback is True
    assert embedding.backend_status.fallback_reason is not None


def test_config_reads_backend_from_env(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_BACKEND", "BGE")
    config = KnowledgeConfig.from_env()
    assert config.embedding_backend == "bge"


def test_ndcg_is_bounded():
    # 单条相关文档，命中第 1 位时为 1.0，未命中为 0.0。
    assert ndcg_at_k(["a"], ["a"], 5) == 1.0
    assert ndcg_at_k(["b", "c"], ["a"], 5) == 0.0
    assert 0.0 <= ndcg_at_k(["b", "a"], ["a"], 5) <= 1.0


def test_source_matching_dedupes_same_document():
    results = [
        {"chunk_id": "c1", "source": "reference/a.md"},
        {"chunk_id": "c2", "source": "reference/a.md"},
        {"chunk_id": "c3", "source": "reference/b.md"},
    ]
    # 同一文档多个 chunk 只保留首次出现，避免 nDCG 重复计分。
    assert _predicted(results, "source") == [
        "reference/a.md",
        "reference/b.md",
    ]


def test_golden_set_entries_are_grounded():
    cases = load_dataset("knowledge/evaluation/golden_set.json")
    assert len(cases) >= 100
    for case in cases:
        assert case.question
        assert case.expected_sources
        assert case.style in {"verbatim", "paraphrase"}


def test_golden_set_v2_reaches_d2_target_and_excludes_rejected_corpus():
    from knowledge.evaluation.build_golden_set_v2 import build_cases, sample_review

    cases, stats = build_cases()

    # D2 目标：≥300 条；问题不重复；文档数单独计数，避免用问法数冒充独立样本。
    assert len(cases) >= 300
    assert len({case["question"] for case in cases}) == len(cases)
    assert stats["documents"] < len(cases)

    # 许可 REJECTED 的红帽教材不得进入评测集（P0-DATA-02 ART-001/002/003）。
    for case in cases:
        assert "RH教材" not in case["expected_sources"][0]
        assert case["license_status"]
        assert case["review_status"] == "unreviewed"

    assert {case["style"] for case in cases} == {"verbatim", "paraphrase", "scenario"}

    # 复核抽样约 30%，且抽样可复现。
    review = sample_review(cases, 0.3)
    assert 0.25 <= len(review) / len(cases) <= 0.35
    assert [case["case_id"] for case in review] == [
        case["case_id"] for case in sample_review(cases, 0.3)
    ]


def test_golden_set_v2_is_deterministic_and_loadable():
    from knowledge.evaluation.build_golden_set_v2 import build_cases

    assert build_cases()[0] == build_cases()[0]

    # 现有 loader 忽略 v2 追加字段，仍可直接评测。
    cases = load_dataset("knowledge/evaluation/golden_set_v2.json")
    assert len(cases) >= 300
    assert all(case.expected_sources for case in cases)

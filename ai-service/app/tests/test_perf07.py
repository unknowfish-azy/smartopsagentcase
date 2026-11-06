"""PERF-07：上下文预算、模型路由与检索缓存的验证。

验收口径里"用同一故障集比较正确率/token/首响应"需要真实 LLM 与故障集，
属于部署环境实验；本文件验证的是机制本身：预算裁剪如实记账、
路由未配置时不假装已路由、缓存键包含租户/权限/版本且降级结果不缓存。
"""

import time

import pytest

from app.core.context_budget import (
    ContextBudget,
    ModelRouter,
    RagQueryCache,
)


# ---------------------------------------------------------------------------
# ContextBudget
# ---------------------------------------------------------------------------

def _result(content: str, score: float) -> dict:
    return {"content": content, "score": score, "source": "s", "version": "v1"}


class TestContextBudget:

    def test_keeps_all_when_within_budget(self):
        budget = ContextBudget(budget_chars=10000, per_item_chars=1000)
        results = [_result("a" * 100, 0.9), _result("b" * 100, 0.8)]
        budgeted, stats = budget.apply(results)
        assert len(budgeted) == 2
        assert stats.dropped == 0
        assert stats.truncated_items == 0
        assert stats.used_chars == 200

    def test_drops_lowest_score_first(self):
        # 预算钳到下限 500：高分两条各 200 装满后，最低分整条丢弃
        budget = ContextBudget(budget_chars=500, per_item_chars=1000)
        results = [
            _result("x" * 200, 0.5),  # 低分：应被丢弃
            _result("y" * 200, 0.9),
            _result("w" * 200, 0.7),
        ]
        budgeted, stats = budget.apply(results)
        assert len(budgeted) == 2
        assert budgeted[0]["content"] == "y" * 200
        assert budgeted[1]["content"] == "w" * 200
        assert stats.dropped == 1
        assert stats.kept == 2

    def test_truncates_overlong_single_item(self):
        # 单条上限钳到下限 200：500 字截断为 200
        budget = ContextBudget(budget_chars=10000, per_item_chars=200)
        results = [_result("z" * 500, 0.9)]
        budgeted, stats = budget.apply(results)
        assert len(budgeted) == 1
        assert len(budgeted[0]["content"]) == 200
        assert stats.truncated_items == 1

    def test_always_keeps_at_least_one_even_over_budget(self):
        budget = ContextBudget(budget_chars=600, per_item_chars=100)
        results = [_result("q" * 500, 0.9)]
        budgeted, stats = budget.apply(results)
        # 预算装不下也截断保一条，不允许"有证据但一条都不给"
        assert len(budgeted) == 1
        assert stats.kept == 1
        assert stats.truncated_items == 1

    def test_empty_input_honest_stats(self):
        budget = ContextBudget()
        budgeted, stats = budget.apply([])
        assert budgeted == []
        assert stats.kept == 0 and stats.dropped == 0

    def test_same_score_keeps_original_order(self):
        budget = ContextBudget(budget_chars=1000, per_item_chars=1000)
        results = [_result("first", 0.5), _result("second", 0.5)]
        budgeted, _ = budget.apply(results)
        assert budgeted[0]["content"] == "first"
        assert budgeted[1]["content"] == "second"


# ---------------------------------------------------------------------------
# ModelRouter
# ---------------------------------------------------------------------------

class TestModelRouter:

    def test_simple_request_routes_to_simple_model(self):
        router = ModelRouter(
            default_model="default-m",
            simple_model="cheap-m",
            complex_model="strong-m",
        )
        decision = router.route("重启 nginx", images=[], evidence_count=3)
        assert decision.complexity == "simple"
        assert decision.model == "cheap-m"
        assert decision.routed is True

    def test_images_force_complex(self):
        router = ModelRouter("default-m", simple_model="cheap-m", complex_model="strong-m")
        decision = router.route("看看这个", images=["a.png"], evidence_count=0)
        assert decision.complexity == "complex"
        assert decision.model == "strong-m"
        assert "images" in decision.reasons

    def test_long_message_forces_complex(self):
        router = ModelRouter("default-m", simple_model="cheap-m", complex_model="strong-m")
        decision = router.route("长" * 401, images=[], evidence_count=0)
        assert decision.complexity == "complex"

    def test_verification_required_forces_complex(self):
        router = ModelRouter("default-m", simple_model="cheap-m", complex_model="strong-m")
        decision = router.route("短问题", verification_required=True)
        assert decision.complexity == "complex"
        assert "verification_required" in decision.reasons

    def test_not_configured_falls_back_honestly(self):
        router = ModelRouter(default_model="mock-model")
        decision = router.route("任意问题", images=["x.png"])
        # 未配置路由模型：不假装已路由，如实回落
        assert decision.model == "mock-model"
        assert decision.routed is False

    def test_partial_config_uses_default_for_missing_side(self):
        router = ModelRouter("default-m", simple_model="cheap-m", complex_model="")
        simple = router.route("简单")
        complex_ = router.route("复杂问题", images=["x.png"])
        assert simple.model == "cheap-m"
        # complex 侧未配置：回落默认而不是报错
        assert complex_.model == "default-m"


# ---------------------------------------------------------------------------
# RagQueryCache
# ---------------------------------------------------------------------------

class TestRagQueryCache:

    def test_cache_key_includes_tenant_user_role_version(self):
        base = dict(
            query="nginx 502",
            tenant="t1",
            user="u1",
            role="USER",
            version="v1",
            top_k=5,
            source=None,
            score_threshold=None,
            vector_weight=None,
            bm25_weight=None,
        )
        key = RagQueryCache.make_key(**base)
        for changed in (
            {"tenant": "t2"},
            {"user": "u2"},
            {"role": "ADMIN"},
            {"version": "v2"},
            {"query": "mysql down"},
            {"top_k": 10},
        ):
            variant = {**base, **changed}
            assert RagQueryCache.make_key(**variant) != key, changed

    def test_hit_and_miss_stats(self):
        cache = RagQueryCache(ttl_sec=60)
        value = {"results": [], "trust_score": 0.0, "retrieval_status": "empty", "degraded": False}
        key = RagQueryCache.make_key("q", tenant="t", user="u", role="r", version=None,
                                     top_k=5, source=None, score_threshold=None,
                                     vector_weight=None, bm25_weight=None)
        assert cache.get(key) is None
        cache.put(key, value)
        assert cache.get(key) is value
        assert cache.stats_dict() == {"hits": 1, "misses": 1, "entries": 1, "evictions": 0}

    def test_ttl_expiry(self):
        now = {"t": 0.0}

        def clock() -> float:
            return now["t"]

        cache = RagQueryCache(ttl_sec=10, clock=clock)
        value = {"results": [], "degraded": False, "retrieval_status": "empty"}
        key = RagQueryCache.make_key("q", tenant="t", user="u", role="r", version=None,
                                     top_k=5, source=None, score_threshold=None,
                                     vector_weight=None, bm25_weight=None)
        cache.put(key, value)
        now["t"] = 9
        assert cache.get(key) is value
        now["t"] = 11
        assert cache.get(key) is None

    def test_degraded_result_is_not_cached(self):
        cache = RagQueryCache(ttl_sec=60)
        key = RagQueryCache.make_key("q", tenant="t", user="u", role="r", version=None,
                                     top_k=5, source=None, score_threshold=None,
                                     vector_weight=None, bm25_weight=None)
        cache.put(key, {"results": [], "degraded": True, "retrieval_status": "unavailable"})
        cache.put(key, {"results": [], "degraded": False, "retrieval_status": "failed"})
        # 一次上游故障不能被固化为"知识库没有"
        assert cache.get(key) is None
        assert cache.stats_dict()["entries"] == 0

    def test_eviction_bounds_entries(self):
        cache = RagQueryCache(ttl_sec=60, max_entries=2)
        common = dict(tenant="t", user="u", role="r", version=None, top_k=5, source=None,
                      score_threshold=None, vector_weight=None, bm25_weight=None)
        value = {"results": [], "degraded": False, "retrieval_status": "empty"}
        for i in range(5):
            cache.put(RagQueryCache.make_key(f"q{i}", **common), value)
        stats = cache.stats_dict()
        assert stats["entries"] == 2
        assert stats["evictions"] == 3


# ---------------------------------------------------------------------------
# ChatService 集成（mock provider + 假 RAG）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_metadata_exposes_perf07_decisions(monkeypatch):
    from app.core.config import settings
    from app.services.chat import ChatService
    from app.schemas.chat import ChatRequest

    monkeypatch.setattr(settings, "llm_model", "mock-model")
    monkeypatch.setattr(settings, "llm_model_simple", "")
    monkeypatch.setattr(settings, "llm_model_complex", "")

    class FakeRAG:
        calls = 0

        async def retrieve(self, **kwargs):
            FakeRAG.calls += 1
            return {
                "results": [{"content": "证据内容", "score": 0.9, "source": "kb", "version": "v1"}],
                "citations": [],
                "evidences": [],
                "trust_score": 0.9,
                "retrieval_status": "ok",
                "degraded": False,
            }

        def build_context(self, results):
            return "\n".join(r["content"] for r in results)

    from app.services.chat import _get_shared_rag_cache
    service = ChatService(rag_service=FakeRAG())
    # 单测内直接复用进程共享缓存
    _get_shared_rag_cache()
    from app.services import chat as chat_module
    chat_module._shared_rag_cache = RagQueryCache(ttl_sec=60)

    request = ChatRequest(
        message="nginx 502 怎么排查",
        use_rag=True,
        metadata={"tenant_id": "t1", "user_id": "u1", "role": "USER"},
    )

    first = await service.chat(request)
    second = await service.chat(request)

    # 同键第二次命中缓存：不再调用 RAG
    assert FakeRAG.calls == 1

    meta1 = first.metadata
    assert meta1["rag_cache"] == "miss"
    assert second.metadata["rag_cache"] == "hit"
    # 路由未配置：如实回落且不假装 routed
    assert meta1["model_routing"]["routed"] is False
    assert meta1["model_routing"]["model"] == "mock-model"
    assert meta1["model_routing"]["complexity"] in ("simple", "complex")
    # 预算记账存在
    assert meta1["context_budget"]["kept"] == 1
    assert meta1["context_budget"]["dropped"] == 0

    # 不同租户不共享缓存结果
    other_tenant = ChatRequest(
        message="nginx 502 怎么排查",
        use_rag=True,
        metadata={"tenant_id": "t2", "user_id": "u1", "role": "USER"},
    )
    await service.chat(other_tenant)
    assert FakeRAG.calls == 2


@pytest.mark.asyncio
async def test_chat_routes_to_complex_model_when_configured(monkeypatch):
    from app.core.config import settings
    from app.services.chat import ChatService
    from app.schemas.chat import ChatRequest

    monkeypatch.setattr(settings, "llm_model", "mock-model")
    monkeypatch.setattr(settings, "llm_model_simple", "cheap-model")
    monkeypatch.setattr(settings, "llm_model_complex", "strong-model")

    captured = {}

    class FakeLLM:
        degraded = False
        effective_provider = "mock"
        degradation_reason = ""

        async def generate(self, prompt, *, system_prompt=None, model=None, **kwargs):
            captured["model"] = model
            return "回答"

        async def generate_stream(self, prompt, *, system_prompt=None, model=None, **kwargs):
            captured["model"] = model
            yield "回答"

    service = ChatService(llm_service=FakeLLM())

    complex_request = ChatRequest(
        message="请分析这张截图里的错误",
        use_rag=False,
        images=["error.png"],
    )
    response = await service.chat(complex_request)
    assert captured["model"] == "strong-model"
    assert response.model == "strong-model"
    assert response.metadata["model_routing"] == {
        "complexity": "complex",
        "model": "strong-model",
        "routed": True,
        "reasons": ["images"],
    }

    simple_request = ChatRequest(message="什么是 inode", use_rag=False)
    response = await service.chat(simple_request)
    assert captured["model"] == "cheap-model"
    assert response.metadata["model_routing"]["complexity"] == "simple"

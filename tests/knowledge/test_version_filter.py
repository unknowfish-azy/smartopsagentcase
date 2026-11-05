"""VERSION-P0-01 完整测试：VersionPolicy / Version / VersionFilter / ACL / INSUFFICIENT / ledger。"""
from knowledge.retrieval.models import RetrievalResult
from knowledge.retrieval.version_filter import (
    VersionFilter,
    VersionPolicy,
    Version,
    LatestResolutionLedger,
    build_filter,
)


# ---------------------------------------------------------------------------
# 旧测试的直接替换：VersionFilter.filter 现在要先实例化
# ---------------------------------------------------------------------------

def test_version_filter_excludes_other_versions():
    results = [
        RetrievalResult("1", "old", 1.0, version="1.0"),
        RetrievalResult("2", "new", 1.0, version="2.0"),
    ]
    f = VersionFilter(policy=VersionPolicy.EXACT, expected_version=Version(component_version="2.0"))
    filtered = f.filter(results)
    assert [item.chunk_id for item in filtered] == ["2"]


# ---------------------------------------------------------------------------
# VersionPolicy.resolve：exact / latest-resolved / unknown 三态
# ---------------------------------------------------------------------------

def test_policy_resolve_none_is_unknown():
    policy, version = VersionPolicy.resolve(None)
    assert policy == VersionPolicy.UNKNOWN
    assert version.is_empty()

def test_policy_resolve_empty_is_unknown():
    policy, version = VersionPolicy.resolve("")
    assert policy == VersionPolicy.UNKNOWN

def test_policy_resolve_latest_is_latest_resolved():
    policy, version = VersionPolicy.resolve("latest")
    assert policy == VersionPolicy.LATEST_RESOLVED

def test_policy_resolve_exact_string():
    policy, version = VersionPolicy.resolve("1.24.0")
    assert policy == VersionPolicy.EXACT
    assert version.component_version == "1.24.0"

def test_policy_resolve_version_obj():
    policy, version = VersionPolicy.resolve(Version(product="nginx", component_version="1.24.0"))
    assert policy == VersionPolicy.EXACT
    assert version.product == "nginx"


# ---------------------------------------------------------------------------
# Version 对象：结构化 vs 兼容 chunk.version="reference"
# ---------------------------------------------------------------------------

def test_version_from_chunk_with_structured_metadata():
    result = RetrievalResult("c1", "d1", 0.9, version="1.24.0",
                             metadata={"version_struct": {"product": "nginx", "component_version": "1.24.0"}})
    v = Version.from_chunk(result)
    assert v.product == "nginx"
    assert v.component_version == "1.24.0"

def test_version_from_chunk_raw_version_string():
    result = RetrievalResult("c2", "nginx content", 0.9, source="ref", document_id="d2", version="reference")
    v = Version.from_chunk(result)
    # "reference" 不是组件版本号，from_chunk 跳过它，得到空 Version（product 可从 source 推断）
    # 现状 version="reference" 是语料摄入时硬编码的 generic 值
    assert v.component_version is None or v.component_version == "reference"

def test_version_is_empty_on_none():
    v = Version()
    assert v.is_empty()


# ---------------------------------------------------------------------------
# UNKNOWN policy → INSUFFICIENT 标记（任务书："目标版本未知时，请求补证或标 INSUFFICIENT"）
# ---------------------------------------------------------------------------

def test_unknown_policy_marks_insufficient():
    results = [
        RetrievalResult("c1", "d1", 0.9, version="reference"),
        RetrievalResult("c2", "d2", 0.8, version="2.0"),
    ]
    f = VersionFilter(policy=VersionPolicy.UNKNOWN)
    filtered = f.filter(results)
    # UNKNOWN 不过滤结果，但标记 insufficient
    assert len(filtered) == 2
    assert f.insufficient is True


# ---------------------------------------------------------------------------
# Tenant/workspace/ACL 骨架：filter_context 匹配 vs 过滤
# ---------------------------------------------------------------------------

def test_tenant_filter_skips_when_context_empty():
    """context 为空 → 不应因为 tenant 过滤丢 chunk（向后兼容）。"""
    results = [RetrievalResult("c1", "d1", 0.9, version="reference")]
    f = VersionFilter(policy=VersionPolicy.EXACT,
                      expected_version=Version(component_version="reference"),
                      filter_context={})
    assert len(f.filter(results)) == 1

def test_tenant_filters_by_metadata():
    results = [
        RetrievalResult("c1", "d1", 0.9, version="reference",
                        metadata={"tenant_id": "t1"}),
        RetrievalResult("c2", "d2", 0.8, version="reference",
                        metadata={"tenant_id": "t2"}),
    ]
    f = VersionFilter(policy=VersionPolicy.EXACT,
                      expected_version=Version(component_version="reference"),
                      filter_context={"tenant_id": "t1"})
    filtered = f.filter(results)
    assert [r.chunk_id for r in filtered] == ["c1"]

def test_workspace_filters_by_metadata():
    results = [
        RetrievalResult("c1", "d1", 0.9, version="reference",
                        metadata={"workspace": "w-prod"}),
        RetrievalResult("c2", "d2", 0.8, version="reference",
                        metadata={"workspace": "w-staging"}),
    ]
    f = VersionFilter(policy=VersionPolicy.EXACT,
                      expected_version=Version(component_version="reference"),
                      filter_context={"workspace_id": "w-prod"})
    filtered = f.filter(results)
    assert [r.chunk_id for r in filtered] == ["c1"]


# ---------------------------------------------------------------------------
# LatestResolutionLedger：latest 必须记账
# ---------------------------------------------------------------------------

def test_latest_ledger_records_entries():
    ledger = LatestResolutionLedger()
    results = [RetrievalResult("c1", "d1", 0.9, version="1.24.0")]
    f = VersionFilter(policy=VersionPolicy.LATEST_RESOLVED,
                      expected_version=Version(component_version="1.24.0"),
                      latest_ledger=ledger,
                      corpus_sha="abc123")
    f.filter(results)
    assert len(ledger) == 1
    assert ledger.last()["corpus_sha"] == "abc123"
    assert ledger.last()["policy"] == "latest-resolved"

def test_latest_ledger_multiple_calls_accumulate():
    ledger = LatestResolutionLedger()
    for i in range(3):
        f = VersionFilter(policy=VersionPolicy.LATEST_RESOLVED,
                          expected_version=Version(component_version="1.24.0"),
                          latest_ledger=ledger,
                          corpus_sha="abc123")
        f.filter([])
    assert len(ledger) == 3


# ---------------------------------------------------------------------------
# build_filter 便捷函数（KnowledgeService.search 的入口）
# ---------------------------------------------------------------------------

def test_build_filter_exact():
    f = build_filter(expected_version="1.24.0", corpus_sha="abc")
    assert f.policy == VersionPolicy.EXACT
    assert f.expected.component_version == "1.24.0"

def test_build_filter_latest():
    f = build_filter(expected_version="latest", corpus_sha="abc")
    assert f.policy == VersionPolicy.LATEST_RESOLVED

def test_build_filter_unknown():
    f = build_filter(expected_version=None, corpus_sha="abc")
    assert f.policy == VersionPolicy.UNKNOWN
    assert f.insufficient is True

def test_build_filter_with_tenant_context():
    f = build_filter(expected_version="1.24.0",
                     filter_context={"tenant_id": "t1", "workspace_id": "w-prod"})
    assert f.filter_context["tenant_id"] == "t1"
    assert f.filter_context["workspace_id"] == "w-prod"


# ---------------------------------------------------------------------------
# 兼容：chunk.version="reference" 匹配 expected="reference"（现状语料全是这个）
# ---------------------------------------------------------------------------

def test_reference_matches_reference():
    results = [RetrievalResult("c1", "d1", 0.9, version="reference")]
    f = VersionFilter(policy=VersionPolicy.EXACT,
                      expected_version=Version(component_version="reference"))
    assert len(f.filter(results)) == 1


# ---------------------------------------------------------------------------
# 验收反例：bm25/hybrid 不再自实现版本过滤 —— 版本过滤统一由 VersionFilter 做
# ---------------------------------------------------------------------------

def test_bm25_search_does_not_filter_version_anymore():
    """bm25.py 已移除版本过滤：传入 version 参数也不再自过滤。

    版本过滤统一由 KnowledgeService.search → build_filter → VersionFilter.filter 做。
    """
    from knowledge.retrieval.bm25 import BM25Retriever
    # BM25Retriever 初始化接受具有 .content 字段的 chunk 对象
    # 用 RetrievalResult 模拟（有 content + version）
    chunks = [
        RetrievalResult(chunk_id="c1", content="nginx reload config", score=0.0,
                        source="ref/nginx", document_id="d1", version="1.24.0"),
        RetrievalResult(chunk_id="c2", content="nginx reload config", score=0.0,
                        source="ref/nginx", document_id="d2", version="1.22.0"),
    ]
    bm25 = BM25Retriever(chunks)
    # 不传 version → 应返回两个（旧代码会因 chunk.version != None 全跳过）
    r_all = bm25.search("nginx reload", top_k=10)
    assert len(r_all) == 2, f"bm25 should return both versions, got {len(r_all)}"
    # 传 version 也不再自过滤（签名保留但不再生效）
    r_v = bm25.search("nginx reload", top_k=10, version="1.24.0")
    assert len(r_v) == 2, f"bm25 no longer filters version internally, got {len(r_v)}"

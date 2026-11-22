"""知识图谱 + 神经符号（P2-7 / B1–B4）单元测试。

对应门禁：
- B-G1 词表封闭：抽取器 / 图不得产出封闭词表之外的实体或关系类型；
- B-G2 边可回溯：每条边必须有 ``source_entry_id``，推导路径逐步可解释；
- B-G3 低置信不入图：被拒边必须进 ``rejected`` 计数，禁止算进命中。

另钉住神经符号硬约束：**没有 ``caused_by`` 边的告警不得产出符号候选**，
只能标 ``neural_only``（禁止把结果写成「符号推理得出」）。
"""

from __future__ import annotations

import json

import pytest

from knowledge.graph.extract import (
    CONF_ACTION,
    CONF_SYMPTOM,
    CONF_WEAK,
    DEFAULT_MIN_CONFIDENCE,
    RuleExtractor,
    parse_entry_payload,
)
from knowledge.graph.reason import (
    CANDIDATE_TYPES,
    DerivationStep,
    ReasoningResult,
    SymbolicReasoner,
)
from knowledge.graph.schema import (
    ENTITY_TYPES,
    RELATION_TYPES,
    Edge,
    Entity,
    ExtractionResult,
    match_entities,
)
from knowledge.graph.store import KnowledgeGraph


# ============================================================ 构造工具
def _edge(
    src_type: str,
    src_id: str,
    dst_type: str,
    dst_id: str,
    relation: str,
    *,
    confidence: float = 0.8,
    source_entry_id: str = "ENTRY-1",
    extractor: str = "test",
) -> Edge:
    return Edge(
        src_type=src_type,
        src_id=src_id,
        dst_type=dst_type,
        dst_id=dst_id,
        relation=relation,
        confidence=confidence,
        source_entry_id=source_entry_id,
        extractor=extractor,
    )


def _entry(
    entry_id: str,
    *,
    title: str = "磁盘只读",
    service: str = "l4-systemd",
    symptoms: str = "磁盘空间耗尽",
    diagnosis: str = "重启服务",
    related: tuple[str, ...] = (),
) -> dict:
    payload = {
        "title": title,
        "symptoms": [symptoms],
        "diagnosis": [diagnosis],
    }
    if related:
        payload["relatedIds"] = list(related)
    return {
        "id": entry_id,
        "title": title,
        "service": service,
        "content": "正文 " + json.dumps(payload, ensure_ascii=False),
    }


def _graph_with_alert(alert_id: str = "INC-A") -> KnowledgeGraph:
    """alert --caused_by--> component:磁盘；service:svc --depends_on--> component:磁盘。"""

    graph = KnowledgeGraph()
    graph.add_edge(_edge("alert", alert_id, "component", "磁盘", "caused_by",
                         confidence=0.8, source_entry_id=alert_id))
    graph.add_edge(_edge("service", "svc", "component", "磁盘", "depends_on",
                         confidence=0.6, source_entry_id=alert_id))
    return graph


# ============================================================ B-G1 词表封闭
def test_match_entities_rejects_unknown_type():
    with pytest.raises(ValueError, match="未知实体类型"):
        match_entities("planet", "火星")


def test_match_entities_returns_deduped_canonical_order():
    names = match_entities("component", "磁盘 内存 磁盘", "cpu 负载")
    assert names == ("磁盘", "内存", "CPU")
    assert len(names) == len(set(names))


def test_match_entities_empty_text_returns_empty():
    assert match_entities("component", "", "   ") == ()


def test_entity_rejects_type_outside_vocabulary():
    with pytest.raises(ValueError, match="封闭词表"):
        Entity("planet", "mars")


def test_entity_rejects_empty_id():
    with pytest.raises(ValueError, match="id 不能为空"):
        Entity("service", "")


def test_edge_rejects_relation_outside_vocabulary():
    with pytest.raises(ValueError, match="关系类型不在封闭词表内"):
        _edge("alert", "a", "component", "磁盘", "explodes")


def test_edge_rejects_endpoint_outside_vocabulary():
    with pytest.raises(ValueError, match="端点类型必须在封闭词表内"):
        _edge("planet", "mars", "component", "磁盘", "caused_by")


def test_edge_rejects_missing_source_entry_id():
    with pytest.raises(ValueError, match="source_entry_id"):
        _edge("alert", "a", "component", "磁盘", "caused_by", source_entry_id="")


def test_edge_rejects_confidence_out_of_range():
    with pytest.raises(ValueError, match="confidence 越界"):
        _edge("alert", "a", "component", "磁盘", "caused_by", confidence=1.5)


def test_extraction_never_emits_out_of_vocabulary_types():
    """B-G1 回归：抽取全量目录，产物类型必须落在封闭词表内。"""

    entries = [
        _entry("INC-A"),
        _entry("INC-B", title="内存 OOM", symptoms="内存耗尽触发 oom", service="l4-oom"),
        _entry("INC-C", title="证书过期", symptoms="tls 证书过期", service="conf-tls"),
    ]
    result = RuleExtractor().extract_catalog(entries)

    assert result.edges
    assert {entity.type for entity in result.entities.values()} <= set(ENTITY_TYPES)
    assert {edge.relation for edge in result.edges} <= set(RELATION_TYPES)


# ============================================================ 声明式字段
def test_declared_emits_confidence_is_one_and_traceable():
    extraction = RuleExtractor().extract_entry(_entry("INC-A", service="l4-systemd"))
    emits = [edge for edge in extraction.edges if edge.relation == "emits"]

    assert len(emits) == 1
    assert emits[0].src_id == "l4-systemd"
    assert emits[0].confidence == 1.0
    assert emits[0].extractor == "declared:service_field"
    assert emits[0].source_entry_id == "INC-A"


def test_declared_cites_links_to_related_entries():
    extraction = RuleExtractor().extract_entry(
        _entry("INC-A", related=("INC-B", "INC-C"))
    )
    cites = [edge for edge in extraction.edges if edge.relation == "cites"]
    targets = {edge.dst_id for edge in cites}

    assert targets == {"INC-B", "INC-C"}
    assert all(edge.confidence == 1.0 for edge in cites)
    assert {entity.id for entity in extraction.entities if entity.type == "alert"} >= {
        "INC-A",
        "INC-B",
        "INC-C",
    }


# ============================================================ B-G3 低置信不入图
def test_weak_action_only_edge_is_rejected_not_in_graph():
    """只在处置文本命中的 caused_by 是 0.4 档，默认阈值下必须拒收。"""

    extraction = RuleExtractor().extract_entry(
        _entry(
            "INC-D",
            symptoms="服务无异常",
            diagnosis="检查磁盘空间并清理",   # 处置里提到 ≠ 病因
        )
    )
    caused = [edge for edge in extraction.edges if edge.relation == "caused_by"]
    rejected = [item for item in extraction.rejected if item["relation"] == "caused_by"]

    assert caused == []
    assert rejected, "被拒边必须落盘"
    assert all(item["confidence"] == CONF_WEAK for item in rejected)


def test_high_threshold_pushes_symptom_edge_into_rejected():
    """min_confidence=0.9 时，0.8 档症状边必须进 rejected 且不入图。"""

    extractor = RuleExtractor(min_confidence=0.9)
    extraction = extractor.extract_entry(_entry("INC-A", symptoms="磁盘空间耗尽"))

    assert [edge for edge in extraction.edges if edge.relation == "caused_by"] == []
    assert any(item["relation"] == "caused_by" for item in extraction.rejected)
    assert CONF_SYMPTOM < 0.9


def test_default_threshold_keeps_symptom_edges():
    assert DEFAULT_MIN_CONFIDENCE <= CONF_SYMPTOM
    extraction = RuleExtractor().extract_entry(_entry("INC-A", symptoms="磁盘空间耗尽"))
    assert [edge for edge in extraction.edges if edge.relation == "caused_by"]


def test_rejected_count_is_recorded_in_result_dict():
    result = RuleExtractor().extract_catalog(
        [
            _entry("INC-A"),
            _entry("INC-D", symptoms="无异常", diagnosis="清理磁盘空间"),
        ]
    )
    payload = result.to_dict()

    assert payload["n_rejected"] == result.rejected_count
    assert payload["n_rejected"] >= 1
    assert "rejected" in payload and payload["rejected"]


def test_rejected_edges_never_reach_graph():
    result = RuleExtractor().extract_catalog(
        [_entry("INC-D", symptoms="无异常", diagnosis="清理磁盘空间")]
    )
    graph = KnowledgeGraph.from_extraction(result)

    assert not graph.has_relation(("alert", "INC-D"), ("component", "磁盘"), "caused_by")


# ============================================================ 抽取器细节
def test_parse_entry_payload_returns_empty_on_unparseable_json():
    assert parse_entry_payload({"content": "没有 JSON 的纯文本"}) == {}
    assert parse_entry_payload({"content": "{ 坏掉的 json "}) == {}
    assert parse_entry_payload({}) == {}


def test_parse_entry_payload_reads_nested_json():
    payload = parse_entry_payload(_entry("INC-A", related=("INC-B",)))
    assert payload["symptoms"] == ["磁盘空间耗尽"]
    assert payload["relatedIds"] == ["INC-B"]


def test_extract_entry_requires_id():
    with pytest.raises(ValueError, match="缺少 id"):
        RuleExtractor().extract_entry({"title": "无 id"})


def test_duplicate_edges_are_deduplicated():
    extraction = RuleExtractor().extract_entry(_entry("INC-A", symptoms="磁盘 磁盘 内存"))
    keys = [
        (edge.src_type, edge.src_id, edge.dst_type, edge.dst_id, edge.relation)
        for edge in extraction.edges
    ]
    assert len(keys) == len(set(keys))


def test_mitigated_by_comes_from_action_text():
    extraction = RuleExtractor().extract_entry(
        _entry("INC-A", diagnosis="重启服务并回滚配置")
    )
    mitigated = [edge for edge in extraction.edges if edge.relation == "mitigated_by"]

    assert {edge.dst_id for edge in mitigated} >= {"重启"}
    assert all(edge.confidence == CONF_ACTION for edge in mitigated)


# ============================================================ 图存储（B-G2）
def test_from_extraction_builds_nodes_and_edges():
    result = RuleExtractor().extract_catalog([_entry("INC-A")])
    graph = KnowledgeGraph.from_extraction(result)

    assert ("alert", "INC-A") in graph.nodes
    assert ("service", "l4-systemd") in graph.nodes
    assert graph.edge_count == len(result.edges)
    assert graph.edge_count > 0


def test_every_edge_is_traceable_to_source_entry():
    """B-G2 硬要求：图里每条边都必须能回溯到来源条目。"""

    result = RuleExtractor().extract_catalog([_entry("INC-A", related=("INC-B",))])
    graph = KnowledgeGraph.from_extraction(result)

    assert all(edge["source_entry_id"] for edge in graph.to_dict()["edges"])
    assert all(edge.source_entry_id == "INC-A" for edge in result.edges)


def test_neighbors_filters_by_relation_and_direction():
    graph = _graph_with_alert()

    out = graph.neighbors(("alert", "INC-A"), relation="caused_by")
    assert [edge.dst_id for edge in out] == ["磁盘"]

    incoming = graph.neighbors(("component", "磁盘"), relation="depends_on", direction="in")
    assert [edge.src_id for edge in incoming] == ["svc"]

    assert graph.neighbors(("alert", "INC-A"), relation="emits") == []


def test_neighbors_rejects_unknown_direction():
    with pytest.raises(ValueError, match="direction"):
        KnowledgeGraph().neighbors(("alert", "a"), direction="sideways")


def test_has_relation():
    graph = _graph_with_alert()
    assert graph.has_relation(("alert", "INC-A"), ("component", "磁盘"), "caused_by")
    assert not graph.has_relation(("alert", "INC-A"), ("component", "磁盘"), "cites")


def test_save_load_roundtrip_preserves_traceability(tmp_path):
    graph = _graph_with_alert()
    path = graph.save(tmp_path / "nested" / "graph.json")

    loaded = KnowledgeGraph.load(path)
    assert loaded.edge_count == graph.edge_count
    assert loaded.to_dict()["edges"] == graph.to_dict()["edges"]
    assert loaded.nodes.keys() == graph.nodes.keys()


# ============================================================ 符号推理硬约束
def test_reasoner_reports_no_candidate_for_unknown_alert():
    result = SymbolicReasoner(_graph_with_alert()).candidates_for_alert("INC-MISSING")
    assert result.status == "no_candidate"
    assert result.candidates == ()


def test_reasoner_marks_neural_only_without_caused_by_edge():
    """硬约束：没有 caused_by 边 → 只能 neural_only，禁止符号结论。"""

    graph = KnowledgeGraph()
    graph.add_edge(_edge("service", "svc", "alert", "INC-X", "emits",
                         confidence=1.0, source_entry_id="INC-X"))

    result = SymbolicReasoner(graph).candidates_for_alert("INC-X")
    assert result.status == "neural_only"
    assert result.candidates == ()
    assert "caused_by" in result.reason


def test_reasoner_no_candidate_when_no_out_edges():
    graph = KnowledgeGraph()
    graph.add_node(Entity("alert", "INC-Y"))

    result = SymbolicReasoner(graph).candidates_for_alert("INC-Y")
    assert result.status == "no_candidate"


def test_reasoner_derives_candidates_with_traceable_paths():
    result = SymbolicReasoner(_graph_with_alert()).candidates_for_alert("INC-A")

    assert result.status == "derived"
    assert result.candidates
    keys = {candidate.key[0] for candidate in result.candidates}
    assert "component" in keys

    for candidate in result.candidates:
        assert candidate.n_paths == len(candidate.paths)
        for path in candidate.paths:
            assert path
            for step in path:
                assert isinstance(step, DerivationStep)
                assert step.source_entry_id == "INC-A"
                assert "src=INC-A" in step.explain()


def test_reasoner_explains_path_end_to_end():
    result = SymbolicReasoner(_graph_with_alert()).candidates_for_alert("INC-A")
    top = result.candidates[0]
    text = top.explain()

    assert "候选 component:磁盘" in text
    assert "--[caused_by" in text
    assert result.to_dict()["candidates"][0]["paths"]


def test_reasoner_follows_depends_on_in_reverse_to_service():
    """component 磁盘 被 service svc 依赖 → 反向扩展出 service 候选。"""

    result = SymbolicReasoner(_graph_with_alert()).candidates_for_alert("INC-A")
    services = [c for c in result.candidates if c.key[0] == "service"]
    assert services, "depends_on 反向扩展应产出 service 候选"
    assert services[0].key == ("service", "svc")


def test_reasoner_candidate_types_are_closed():
    assert set(CANDIDATE_TYPES) <= set(ENTITY_TYPES)


def test_reasoner_rejects_invalid_max_hops():
    with pytest.raises(ValueError, match="max_hops"):
        SymbolicReasoner(_graph_with_alert(), max_hops=0)


def test_reasoner_honours_hop_limit():
    """max_hops=1 时只做 caused_by 一跳，不应反向扩到 service。"""

    result = SymbolicReasoner(_graph_with_alert(), max_hops=1).candidates_for_alert("INC-A")
    assert {candidate.key[0] for candidate in result.candidates} == {"component"}


def test_reasoner_sorts_candidates_by_score_then_paths():
    graph = KnowledgeGraph()
    graph.add_edge(_edge("alert", "INC-A", "component", "磁盘", "caused_by",
                         confidence=0.8, source_entry_id="INC-A"))
    graph.add_edge(_edge("alert", "INC-A", "component", "内存", "caused_by",
                         confidence=0.95, source_entry_id="INC-A"))

    result = SymbolicReasoner(graph).candidates_for_alert("INC-A")
    scores = [candidate.score for candidate in result.candidates]
    assert scores == sorted(scores, reverse=True)
    assert result.candidates[0].key == ("component", "内存")


def test_reasoning_result_shape():
    result = ReasoningResult(
        alert_id="INC-A", status="derived", candidates=(), visited_nodes=3, reason="r"
    )
    payload = result.to_dict()
    assert payload["alert_id"] == "INC-A"
    assert payload["status"] == "derived"
    assert payload["visited_nodes"] == 3

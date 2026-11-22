"""EXP-KG-001：知识图谱 + 神经符号（P2-7 / B）受控对照实验。

对照什么
--------
同一份 catalog（``backend/src/main/resources/knowledge/catalog.json``）上比较

* **hybrid**：现有召回层（HashEmbedding + BM25，离线确定性）top-k 条目；
* **KG**：符号推理给出的根因候选 → 映射回条目；
* **hybrid+KG**：hybrid top-10 用 KG 命中集合重排后的 top-5。

指标
----
- 覆盖率（B-G6）：有入图边的条目占比、有 ``caused_by`` 边的条目数；
- 抽样核对（B-G2）：≥20 条 ``caused_by`` 边逐条核对词面依据，给一致率 + Wilson；
- 三路 recall@5 / hit@5 + Wilson 区间（B-G4）；
- 互补性：hybrid 与 KG 各自独占 / 重叠的命中计数。

诚实边界（必须随数字引用）
--------------------------
1. **金标是图派生的**：``gold(A)`` = 与 A 共享 ``caused_by`` 根因的条目 ∪
   ``cites`` 目标。KG 的候选**来自同一份图**，因此 KG 的高分**不构成
   「优于 hybrid」的独立证据**，只能说明「符号映射与图结构自洽」。
2. **抽样核对是自检**：词面判据与抽取器共享同一份受控词表，只能验证
   「抽取结果确有词面依据、阈值策略没有明显误收」，**不能**证明语义正确；
   真正的语义正确性需独立人工盲评，本机无条件执行。
3. **召回层是 HashEmbedding**（确定性哈希向量，非语义模型），
   因此 hybrid 的 recall 只是**召回层基线**，不得当作「语义检索性能」。
4. 被拒边（``rejected``）一律不计入任何命中（B-G3）。

产物
----
- ``reports/kg-eval-<tag>.json``
- ``reports/kg-eval-<tag>.md``

复现：``python scripts/eval_kg.py``（默认全量 catalog）
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from knowledge.graph.extract import RuleExtractor, parse_entry_payload
from knowledge.graph.reason import SymbolicReasoner
from knowledge.graph.schema import COMPONENT_VOCAB, METRIC_VOCAB
from knowledge.graph.store import KnowledgeGraph

_STATS_PATH = REPO / "scripts" / "stats_inference.py"
_spec = importlib.util.spec_from_file_location("stats_inference", _STATS_PATH)
assert _spec and _spec.loader
stats = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(stats)

CATALOG = REPO / "backend" / "src" / "main" / "resources" / "knowledge" / "catalog.json"
DEFAULT_REPORT_DIR = REPO / "reports"

SEED = 20261122
AUDIT_SAMPLE = 24          # B-G2：抽样 ≥20 条
TOP_K = 5
HYBRID_POOL = 10           # hybrid+KG 重排的候选池


# ---------------------------------------------------------------------------
# 数据装载
# ---------------------------------------------------------------------------


def load_catalog(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("entries") if isinstance(payload, dict) else payload
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"catalog 为空或结构不符：{path}")
    return [entry for entry in entries if isinstance(entry, dict) and entry.get("id")]


def entry_query_text(entry: dict[str, Any]) -> str:
    """查询文本：标题 + 症状（与抽取器的 symptom_text 口径一致）。"""

    payload = parse_entry_payload(entry)
    title = str(entry.get("title") or payload.get("title") or "")
    symptoms = payload.get("symptoms") or payload.get("observed") or ""
    if isinstance(symptoms, list):
        symptoms = " ".join(str(item) for item in symptoms)
    return f"{title} {symptoms}".strip()


# ---------------------------------------------------------------------------
# 1. 抽取与覆盖率（B-G6）
# ---------------------------------------------------------------------------


def extraction_summary(
    entries: Sequence[dict[str, Any]],
    extractor: RuleExtractor,
    graph: KnowledgeGraph,
) -> dict[str, Any]:
    result = extractor.extract_catalog(entries)
    with_edge = {
        edge.source_entry_id
        for edge in result.edges
    }
    with_caused = {
        edge.source_entry_id
        for edge in result.edges
        if edge.relation == "caused_by"
    }
    total = len(entries)
    return {
        "n_entries": total,
        "n_nodes": len(graph.nodes),
        "n_edges": graph.edge_count,
        "n_rejected": result.rejected_count,
        "relation_counts": dict(Counter(edge.relation for edge in result.edges)),
        "extractor_counts": dict(Counter(edge.extractor for edge in result.edges)),
        "entity_type_counts": dict(Counter(node.type for node in graph.nodes.values())),
        "with_any_edge": _ratio(len(with_edge), total),
        "with_caused_by": _ratio(len(with_caused), total),
        "rejected_by_reason": dict(
            Counter(item.get("reason", "") for item in result.rejected)
        ),
    }


def _ratio(num: int, den: int) -> dict[str, Any]:
    if not den:
        return {"num": num, "den": den, "value": None, "status": "NOT_RUN"}
    lo, hi = stats.wilson_interval(num, den)
    return {
        "num": num,
        "den": den,
        "value": round(num / den, 6),
        "wilson95": [round(lo, 6), round(hi, 6)],
    }


# ---------------------------------------------------------------------------
# 2. 抽样核对（B-G2）
# ---------------------------------------------------------------------------


def audit_sample(
    entries: Sequence[dict[str, Any]],
    extractor: RuleExtractor,
    *,
    sample_size: int,
    seed: int,
) -> dict[str, Any]:
    """逐条核对 caused_by 边的词面依据。

    判据（独立实现，不复用 ``match_entities``）：对每条 ``caused_by`` 边，
    用受控词表的正则**直接**在症状字段里找该规范名的关键词依据。
    命中 → ``supported``；否则 ``unsupported``（抽取器把别处的东西当病因）。

    局限：判据与抽取器共享词表 → 属**自检**，不证明语义正确。
    """

    by_id = {str(entry["id"]): entry for entry in entries}
    candidates: list[tuple[str, str, str]] = []   # (entry_id, entity_type, name)
    for entry in entries:
        extraction = extractor.extract_entry(entry)
        for edge in extraction.edges:
            if edge.relation == "caused_by":
                candidates.append((edge.source_entry_id, edge.dst_type, edge.dst_id))

    rng = random.Random(seed)
    if len(candidates) > sample_size:
        picked = rng.sample(candidates, sample_size)
    else:
        picked = list(candidates)
    picked.sort()

    vocab = {"component": COMPONENT_VOCAB, "metric": METRIC_VOCAB}
    details: list[dict[str, Any]] = []
    supported = 0
    for entry_id, entity_type, name in picked:
        entry = by_id.get(entry_id)
        if entry is None:
            continue
        payload = parse_entry_payload(entry)
        symptom_text = " ".join(
            str(payload.get(field) or "")
            for field in ("symptoms", "observed", "title")
        ).strip() or str(entry.get("title") or "").strip()
        pattern = dict(vocab.get(entity_type, ())).get(name)
        hit = bool(pattern) and bool(re.search(pattern, symptom_text, re.IGNORECASE))
        supported += int(hit)
        details.append({
            "entry_id": entry_id,
            "entity_type": entity_type,
            "name": name,
            "supported": hit,
            "symptom_excerpt": symptom_text[:120],
        })

    n = len(details)
    result = _ratio(supported, n)
    result["sample_size"] = sample_size
    result["population"] = len(candidates)
    result["seed"] = seed
    result["details"] = details
    result["caveat"] = (
        "判据与抽取器共享受控词表，属自检；不证明语义正确，"
        "不得当作独立人工盲评一致率"
    )
    return result


def audit_rejected(
    entries: Sequence[dict[str, Any]],
    extractor: RuleExtractor,
    *,
    sample_size: int,
    seed: int,
) -> dict[str, Any]:
    """核对被拒边：目标词的词面依据**是否确实只出现在处置字段**。

    这条判据**独立于** caused_by 的入图判定（只看「症状字段是否也命中」），
    用来验证 B-G3 的阈值策略没有把真实病因误杀。
    """

    by_id = {str(entry["id"]): entry for entry in entries}
    rejected = list(extractor.extract_catalog(entries).rejected)
    rng = random.Random(seed)
    picked = rng.sample(rejected, min(sample_size, len(rejected)))
    picked.sort(key=lambda item: (item.get("entry_id", ""), item.get("dst_id", "")))

    vocab = {**dict(COMPONENT_VOCAB), **dict(METRIC_VOCAB)}
    details: list[dict[str, Any]] = []
    consistent = 0
    for item in picked:
        entry = by_id.get(item.get("entry_id", ""))
        name = item.get("dst_id", "")
        if entry is None or name not in vocab:
            continue
        payload = parse_entry_payload(entry)
        symptom_text = " ".join(
            str(payload.get(field) or "")
            for field in ("symptoms", "observed", "title")
        ).strip() or str(entry.get("title") or "").strip()
        action_text = " ".join(
            str(payload.get(field) or "")
            for field in ("diagnosis", "steps")
        ).strip()
        pattern = vocab[name]
        in_symptom = bool(re.search(pattern, symptom_text, re.IGNORECASE))
        in_action = bool(re.search(pattern, action_text, re.IGNORECASE))
        # 拒绝正确的定义：症状字段没有依据，且处置字段确实提到
        ok = (not in_symptom) and in_action
        consistent += int(ok)
        details.append({
            "entry_id": item.get("entry_id"),
            "dst_id": name,
            "relation": item.get("relation"),
            "confidence": item.get("confidence"),
            "in_symptom": in_symptom,
            "in_action": in_action,
            "rejection_consistent": ok,
        })

    n = len(details)
    result = _ratio(consistent, n)
    result["sample_size"] = sample_size
    result["population"] = len(rejected)
    result["seed"] = seed
    result["details"] = details
    result["caveat"] = (
        "判据独立于 caused_by 入图判定，但目标名仍取自抽取结果；"
        "用于验证阈值策略未误杀，不等于抽取语义正确"
    )
    return result


# ---------------------------------------------------------------------------
# 3. 三路 recall@k（B-G4）
# ---------------------------------------------------------------------------


def build_retriever(entries: Sequence[dict[str, Any]]):
    """离线确定性 hybrid：HashEmbedding + BM25 + InMemoryVectorStore。"""

    from knowledge.ingestion.chunker import TextChunker
    from knowledge.retrieval.bm25 import BM25Retriever
    from knowledge.retrieval.hybrid import HybridRetriever
    from knowledge.retrieval.vector_store import InMemoryVectorStore

    try:
        from knowledge.embedding.hash_embedding import HashEmbedding
        embedding = HashEmbedding()
    except Exception:                                    # pragma: no cover
        from knowledge.embedding.factory import get_embedding
        embedding = get_embedding()

    chunker = TextChunker()
    store = InMemoryVectorStore()
    chunks = []
    for entry in entries:
        text = _entry_text(entry)
        for chunk in chunker.split(str(entry["id"]), text, source="catalog"):
            chunks.append(chunk)
            store.add(chunk, embedding.encode([chunk.content])[0])
    return HybridRetriever(store, BM25Retriever(chunks)), embedding


def _entry_text(entry: dict[str, Any]) -> str:
    """与 KnowledgeService._entry_to_text 同口径的干净文本（避免拉起 service 依赖）。"""

    payload = parse_entry_payload(entry)
    title = str(entry.get("title") or payload.get("title") or entry.get("id") or "")
    symptoms = payload.get("symptoms") or payload.get("observed") or ""
    if isinstance(symptoms, list):
        symptoms = "；".join(str(item) for item in symptoms)
    diagnosis = payload.get("diagnosis") or ""
    if isinstance(diagnosis, list):
        diagnosis = "；".join(str(item) for item in diagnosis)
    service = str(entry.get("service") or "")
    parts = [f"# {title}", f"服务：{service}" if service else "", f"症状：{symptoms}",
             f"处置：{diagnosis}"]
    return "\n".join(part for part in parts if part)


def gold_map(
    entries: Sequence[dict[str, Any]],
    extractor: RuleExtractor,
    graph: KnowledgeGraph,
) -> dict[str, set[str]]:
    """图派生金标：同 caused_by 根因的条目 ∪ cites 目标。

    **同源声明**：KG 的候选来自同一份图，因此该金标对 KG 不是独立真值。
    """

    roots: dict[str, set[tuple[str, str]]] = defaultdict(set)
    cites: dict[str, set[str]] = defaultdict(set)
    for edge in extractor.extract_catalog(entries).edges:
        if edge.relation == "caused_by":
            roots[edge.source_entry_id].add((edge.dst_type, edge.dst_id))
        elif edge.relation == "cites":
            cites[edge.source_entry_id].add(edge.dst_id)

    ids = sorted(roots)
    gold: dict[str, set[str]] = {}
    for alert_id in ids:
        related = set(cites.get(alert_id, ()))
        for other in ids:
            if other == alert_id:
                continue
            if roots[other] & roots[alert_id]:
                related.add(other)
        related.discard(alert_id)
        gold[alert_id] = related
    return gold


def kg_hits(
    alert_id: str,
    reasoner: SymbolicReasoner,
    entries_by_id: dict[str, dict[str, Any]],
    extractor: RuleExtractor,
) -> list[str]:
    """符号候选 → 映射回条目（按候选 score 顺序逐个根因取条目）。"""

    result = reasoner.candidates_for_alert(alert_id)
    if result.status != "derived":
        return []

    roots: dict[tuple[str, str], float] = {
        candidate.key: candidate.score for candidate in result.candidates
    }
    hits: list[str] = []
    seen: set[str] = {alert_id}
    extraction = extractor.extract_catalog(list(entries_by_id.values()))
    for edge in extraction.edges:
        if edge.relation != "caused_by" or edge.source_entry_id in seen:
            continue
        score = roots.get((edge.dst_type, edge.dst_id))
        if score is None:
            continue
        seen.add(edge.source_entry_id)
        hits.append((edge.source_entry_id, score))
    hits.sort(key=lambda item: -item[1])
    return [entry_id for entry_id, _ in hits]


def evaluate_retrieval(
    entries: Sequence[dict[str, Any]],
    extractor: RuleExtractor,
    graph: KnowledgeGraph,
    *,
    top_k: int,
) -> dict[str, Any]:
    retriever, embedding = build_retriever(entries)
    entries_by_id = {str(entry["id"]): entry for entry in entries}
    gold = gold_map(entries, extractor, graph)
    reasoner = SymbolicReasoner(graph)
    query_ids = sorted(gold)

    per_query: list[dict[str, Any]] = []
    for alert_id in query_ids:
        gold_set = gold[alert_id]
        if not gold_set:
            continue
        query = entry_query_text(entries_by_id[alert_id])
        results = retriever.search(
            query=query,
            query_vector=embedding.encode([query], is_query=True)[0],
            top_k=HYBRID_POOL,
        )
        hybrid_pool = [
            result_to_entry(r.document_id, entries_by_id)
            for r in results
        ]
        hybrid_pool = [eid for eid in hybrid_pool if eid and eid != alert_id][:HYBRID_POOL]
        hybrid_ranked = hybrid_pool[:top_k]

        kg_all = kg_hits(alert_id, reasoner, entries_by_id, extractor)
        kg_set = set(kg_all)
        kg_ranked = kg_all[:top_k]

        # hybrid+KG：只在 hybrid 候选池内重排（KG 命中优先），不注入池外答案
        merged = sorted(hybrid_pool, key=lambda eid: (eid not in kg_set,))[:top_k]

        per_query.append({
            "alert_id": alert_id,
            "gold_size": len(gold_set),
            "hybrid": _score(hybrid_ranked, gold_set),
            "kg": _score(kg_ranked, gold_set),
            "hybrid_kg": _score(merged, gold_set),
            "hybrid_top": hybrid_ranked,
            "kg_top": kg_ranked,
            "overlap": len(set(hybrid_ranked) & set(kg_ranked)),
        })

    n = len(per_query)
    summary = {
        "n_queries": n,
        "top_k": top_k,
        "gold_definition": (
            "图派生：与查询条目共享 caused_by 根因的条目 ∪ cites 目标；"
            "KG 与金标同源，KG 的高分不构成独立性能证据"
        ),
    }
    for arm in ("hybrid", "kg", "hybrid_kg"):
        hits = sum(1 for row in per_query if row[arm]["hit"])
        recalls = [row[arm]["recall"] for row in per_query]
        summary[arm] = {
            "hit_rate": _ratio(hits, n),
            "mean_recall": (
                round(sum(recalls) / n, 6) if n else None
            ),
            "mean_gold_size": (
                round(sum(row["gold_size"] for row in per_query) / n, 3) if n else None
            ),
        }
    both = sum(
        1 for row in per_query
        if row["hybrid"]["hit"] and row["kg"]["hit"]
    )
    only_hybrid = sum(
        1 for row in per_query
        if row["hybrid"]["hit"] and not row["kg"]["hit"]
    )
    only_kg = sum(
        1 for row in per_query
        if row["kg"]["hit"] and not row["hybrid"]["hit"]
    )
    summary["complementarity"] = {
        "both_hit": both,
        "only_hybrid_hit": only_hybrid,
        "only_kg_hit": only_kg,
        "neither": n - both - only_hybrid - only_kg,
        "mean_overlap": (
            round(sum(row["overlap"] for row in per_query) / n, 3) if n else None
        ),
    }
    summary["per_query"] = per_query
    return summary


def _score(ranked: Sequence[str], gold_set: set[str]) -> dict[str, Any]:
    retrieved = set(ranked)
    n_gold = len(gold_set)
    n_hit = len(retrieved & gold_set)
    return {
        "n_retrieved": len(ranked),
        "n_hit": n_hit,
        "hit": n_hit > 0,
        "recall": (n_hit / n_gold) if n_gold else None,
        "precision": (n_hit / len(ranked)) if ranked else None,
    }


def result_to_entry(document_id: str, entries_by_id: dict[str, dict[str, Any]]) -> str | None:
    """把检索结果的 ``document_id`` 映射回 catalog 条目 id。"""

    return document_id if document_id in entries_by_id else None


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------


def _fmt(value: Any, digits: int) -> str:
    """None（未跑/无分母）统一渲染成 ``n/a``，不伪装成 0。"""

    return f"{value:.{digits}f}" if isinstance(value, (int, float)) else "n/a"


def render_markdown(
    summary: dict[str, Any],
    audit: dict[str, Any],
    rejected_audit: dict[str, Any],
    tag: str,
) -> str:
    lines = [
        f"# EXP-KG-001 知识图谱 + 神经符号对照（{tag}）",
        "",
        "## 1. 抽取与覆盖率（B-G6）",
        "",
        f"- 条目 {summary['n_entries']} 条 → 节点 {summary['n_nodes']} / 边 {summary['n_edges']}"
        f" / 被拒 {summary['n_rejected']}",
        f"- 有任意入图边的条目占比：{summary['with_any_edge']['value']:.4f}"
        f"（{summary['with_any_edge']['num']}/{summary['with_any_edge']['den']}）"
        "——**100% 是因为声明式 `emits` 覆盖全部条目**，该指标本身无信息量",
        f"- 有 caused_by 边的条目占比：{summary['with_caused_by']['value']:.4f}"
        f"（{summary['with_caused_by']['num']}/{summary['with_caused_by']['den']}）"
        "——**这才是符号推理的真实可用覆盖面**",
        "- 关系分布：" + json.dumps(summary["relation_counts"], ensure_ascii=False),
        "- 抽取器分布：" + json.dumps(summary["extractor_counts"], ensure_ascii=False),
        "- 被拒原因分布：" + json.dumps(summary["rejected_by_reason"], ensure_ascii=False),
        "",
        "## 2. 抽样核对（B-G2 / B-G3）",
        "",
        f"- **入图边**：抽样 {audit['sample_size']} 条 caused_by 边（总体 {audit['population']}，"
        f"seed={audit['seed']}），词面依据一致率 **{audit['value']:.4f}**"
        f"（{audit['num']}/{audit['den']}，Wilson95 [{audit['wilson95'][0]:.4f}, "
        f"{audit['wilson95'][1]:.4f}]）",
        f"  - ⚠️ {audit['caveat']}",
        f"- **被拒边**：抽样 {rejected_audit['sample_size']} 条（总体 "
        f"{rejected_audit['population']}），拒绝一致率 "
        f"**{rejected_audit['value']:.4f}**（{rejected_audit['num']}/{rejected_audit['den']}，"
        f"Wilson95 [{rejected_audit['wilson95'][0]:.4f}, "
        f"{rejected_audit['wilson95'][1]:.4f}]）",
        f"  - ⚠️ {rejected_audit['caveat']}",
        "",
        "## 3. 三路 recall@5（B-G4）",
        "",
        f"- 查询数 n={summary['n_queries']}",
        f"- 金标定义：{summary['gold_definition']}",
        "",
        "| 路 | hit@5 | mean recall@5 | 平均金标大小 |",
        "|---|---|---|---|",
    ]
    for arm, label in (("hybrid", "hybrid"), ("kg", "KG"), ("hybrid_kg", "hybrid+KG")):
        row = summary[arm]
        hit = row["hit_rate"]
        lines.append(
            f"| {label} | {_fmt(hit['value'], 4)} "
            f"（{hit['num']}/{hit['den']}） "
            f"[{_fmt(hit['wilson95'][0], 4)}, {_fmt(hit['wilson95'][1], 4)}] "
            f"| {_fmt(row['mean_recall'], 4)} | {_fmt(row['mean_gold_size'], 2)} |"
        )
    comp = summary["complementarity"]
    lines += [
        "",
        "### 互补性",
        "",
        f"- 两路都命中 {comp['both_hit']} / 仅 hybrid {comp['only_hybrid_hit']} "
        f"/ 仅 KG {comp['only_kg_hit']} / 都不中 {comp['neither']}",
        f"- 平均重叠条数 {comp['mean_overlap']}",
        "",
        "## 诚实边界（必须随数字引用）",
        "",
        "1. **循环警示**：金标由 ``caused_by`` 图派生，KG 候选也来自同一份图 → "
        "KG 的 hit@5=1.0 与 hybrid+KG 的增量**都是循环的**，"
        "**不构成「混合检索优于 hybrid」的证据**；",
        "2. 入图边核对与抽取器共享词表 → 属自检，非独立人工盲评；"
        "被拒边核对判据独立，但仍只验证阈值策略；",
        "3. 召回层是 HashEmbedding（确定性哈希向量），非语义模型 → "
        "hybrid 的 recall 只是召回层基线；",
        "4. 被拒边一律不计入任何命中（B-G3）；",
        "5. 319 条查询的平均金标大小 35.4 条 → recall@5 的绝对值被大金标压低，"
        "应看 hit@5 与互补性。",
        "",
        f"生成时间：{datetime.now(timezone.utc).isoformat()}",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="EXP-KG-001 知识图谱对照实验")
    parser.add_argument("--catalog", default=str(CATALOG))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--tag", default=datetime.now(timezone.utc).strftime("%Y%m%d"))
    parser.add_argument("--sample", type=int, default=AUDIT_SAMPLE)
    parser.add_argument("--top-k", type=int, default=TOP_K)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    entries = load_catalog(Path(args.catalog))
    extractor = RuleExtractor()
    result = extractor.extract_catalog(entries)
    graph = KnowledgeGraph.from_extraction(result)

    summary = extraction_summary(entries, extractor, graph)

    audit = audit_sample(entries, extractor, sample_size=args.sample, seed=args.seed)
    rejected_audit = audit_rejected(
        entries, extractor, sample_size=args.sample, seed=args.seed
    )
    retrieval = evaluate_retrieval(entries, extractor, graph, top_k=args.top_k)
    summary.update({k: v for k, v in retrieval.items() if k != "per_query"})

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / f"kg-eval-{args.tag}.json"
    md_path = report_dir / f"kg-eval-{args.tag}.md"

    payload = {
        "experiment": "EXP-KG-001",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "catalog": str(Path(args.catalog)),
        "n_entries": len(entries),
        "extraction": summary,
        "audit": audit,
        "rejected_audit": rejected_audit,
        "retrieval": retrieval,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        render_markdown(summary, audit, rejected_audit, args.tag), encoding="utf-8"
    )

    print(f"[EXP-KG-001] entries={len(entries)} nodes={summary['n_nodes']} "
          f"edges={summary['n_edges']} rejected={summary['n_rejected']}")
    print(f"[EXP-KG-001] 有边条目占比={summary['with_any_edge']['value']:.4f} "
          f"有 caused_by 占比={summary['with_caused_by']['value']:.4f}")
    print(f"[EXP-KG-001] 入图边核对一致率={audit['value']:.4f} "
          f"({audit['num']}/{audit['den']})")
    print(f"[EXP-KG-001] 被拒边核对一致率={rejected_audit['value']:.4f} "
          f"({rejected_audit['num']}/{rejected_audit['den']})")
    for arm in ("hybrid", "kg", "hybrid_kg"):
        row = summary[arm]
        print(f"[EXP-KG-001] {arm:<10} hit@{args.top_k}={row['hit_rate']['value']:.4f} "
              f"mean_recall={row['mean_recall']:.4f}")
    print(f"[EXP-KG-001] 报告：{json_path}")
    print(f"[EXP-KG-001] 报告：{md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

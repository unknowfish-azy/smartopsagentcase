"""规则抽取器（P2-7 / B2）。

方案口径：`docs/design/p2-7-causal-kg-debate-v1/DESIGN.md` §3.3。

抽取策略（诚实优先）
------------------

1. **声明式字段优先**（``confidence=1.0``，``extractor="declared:*"``）：
   - ``emits``：条目的 ``service`` 字段 → 告警条目；
   - ``cites``：条目内层 JSON 的 ``relatedIds`` → 同库条目。
2. **规则抽取**（正则 + 受控词表，按**命中位置**分配置信度）：

   | 关系 | 命中位置 | confidence |
   |---|---|---|
   | `caused_by`（alert→component/metric） | `symptoms` / `observed` / `title` | **0.8** |
   | `caused_by` | `diagnosis` / `steps`（处置里提到 ≠ 病因） | **0.4** → 默认**拒收** |
   | `mitigated_by`（alert→run） | `diagnosis` / `steps` | **0.6** |
   | `mitigated_by` | `symptoms` / `observed` | **0.4** → 默认**拒收** |
   | `depends_on`（service→component） | `symptoms` / `observed` | **0.6** |

3. **低于阈值一律不入图**，写进 ``rejected``（门禁 B-G3）。

**不做 LLM 抽取**：本机无稳定离线抽取模型，且用户级偏好要求知识条目不出本机。
``LLMExtractor`` 只在有显式注入时可用（协议上预留，不伪造）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from .schema import (
    Edge,
    Entity,
    ExtractionResult,
    match_entities,
)

# 置信度分档（按命中位置）
CONF_SYMPTOM = 0.8
CONF_ACTION = 0.6
CONF_WEAK = 0.4

DEFAULT_MIN_CONFIDENCE = 0.5

_SYMPTOM_FIELDS = ("symptoms", "observed", "title")
_ACTION_FIELDS = ("diagnosis", "steps")


@dataclass(frozen=True)
class EntryExtraction:
    """单条条目的抽取产物。"""

    entry_id: str
    entities: tuple[Entity, ...]
    edges: tuple[Edge, ...]
    rejected: tuple[dict, ...]
    n_components: int = 0
    n_metrics: int = 0
    n_runs: int = 0


def parse_entry_payload(entry: dict[str, Any]) -> dict[str, Any]:
    """取出条目正文里的内层 JSON（``content`` 是一段含 JSON 的文本）。

    解析失败返回 ``{}``（不抛异常）——9/737 条内层 JSON 不可解析属已知事实。
    """

    content = entry.get("content") or ""
    match = re.search(r"\{.*\}", content, re.S)
    if not match:
        return {}
    try:
        payload = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _field_text(payload: dict[str, Any], fields: Iterable[str]) -> str:
    chunks: list[str] = []
    for name in fields:
        value = payload.get(name)
        if isinstance(value, str):
            chunks.append(value)
        elif isinstance(value, list):
            chunks.extend(str(item) for item in value)
    return "\n".join(chunks)


@dataclass
class RuleExtractor:
    """规则抽取器：词表封闭、置信度分档、拒绝计数。"""

    min_confidence: float = DEFAULT_MIN_CONFIDENCE
    extract_llm: Any = None

    def extract_entry(self, entry: dict[str, Any]) -> EntryExtraction:
        entry_id = str(entry.get("id") or "").strip()
        if not entry_id:
            raise ValueError("条目缺少 id")

        payload = parse_entry_payload(entry)
        title = str(entry.get("title") or payload.get("title") or "")
        symptom_text = _field_text(payload, ("symptoms", "observed")) or title
        action_text = _field_text(payload, _ACTION_FIELDS)
        service = str(entry.get("service") or "").strip()

        entities: dict[tuple[str, str], Entity] = {
            ("alert", entry_id): Entity("alert", entry_id, title or entry_id),
        }
        edges: list[Edge] = []
        rejected: list[dict] = []

        def _add(edge: Edge | None, *, reject_reason: str, rejected_edge: Edge | None) -> None:
            if edge is not None and edge.confidence >= self.min_confidence:
                edges.append(edge)
                return
            # B-G3：任何因阈值被拒的边都必须落盘（含症状边被高阈值拒收的情况），
            # 否则「未入图」会被静默吞掉，无法审计。
            target = rejected_edge if rejected_edge is not None else edge
            if target is not None:
                rejected.append({
                    "entry_id": entry_id,
                    "relation": target.relation,
                    "src_id": target.src_id,
                    "dst_id": target.dst_id,
                    "confidence": target.confidence,
                    "reason": reject_reason or f"低于阈值 {self.min_confidence}",
                })

        if service:
            entities[("service", service)] = Entity("service", service, service)
            _add(
                Edge("service", service, "alert", entry_id, "emits",
                     1.0, entry_id, "declared:service_field", service),
                reject_reason="",
                rejected_edge=None,
            )

        # cites：内层 JSON 的 relatedIds（声明式）
        related = payload.get("relatedIds") or []
        for target in related:
            if not isinstance(target, str) or not target:
                continue
            entities[("alert", target)] = Entity("alert", target, target)
            _add(
                Edge("alert", entry_id, "alert", target, "cites",
                     1.0, entry_id, "declared:relatedIds", target),
                reject_reason="",
                rejected_edge=None,
            )

        # caused_by：alert → component / metric
        for entity_type in ("component", "metric"):
            canonical = match_entities(entity_type, symptom_text)
            weak = match_entities(entity_type, action_text)
            for name in canonical:
                entities[(entity_type, name)] = Entity(entity_type, name, name)
                _add(
                    Edge("alert", entry_id, entity_type, name, "caused_by",
                         CONF_SYMPTOM, entry_id, f"rule:{entity_type}_vocab",
                         symptom_text[:120]),
                    reject_reason="",
                    rejected_edge=None,
                )
            for name in weak:
                if name in canonical:
                    continue
                entities[(entity_type, name)] = Entity(entity_type, name, name)
                candidate = Edge("alert", entry_id, entity_type, name, "caused_by",
                                 CONF_WEAK, entry_id, f"rule:{entity_type}_vocab",
                                 action_text[:120])
                _add(
                    None,
                    reject_reason=(
                        f"仅在处置文本（diagnosis/steps）命中，{self.min_confidence} 阈值下不入图"
                    ),
                    rejected_edge=candidate,
                )

        # mitigated_by：alert → run（从处置文本）
        for name in match_entities("run", action_text):
            entities[("run", name)] = Entity("run", name, name)
            _add(
                Edge("alert", entry_id, "run", name, "mitigated_by",
                     CONF_ACTION, entry_id, "rule:run_vocab", action_text[:120]),
                reject_reason="",
                rejected_edge=None,
            )

        # depends_on：service → component
        if service:
            for name in match_entities("component", symptom_text):
                candidate = Edge("service", service, "component", name, "depends_on",
                                 CONF_ACTION, entry_id, "rule:component_vocab",
                                 symptom_text[:120])
                _add(
                    candidate,
                    reject_reason="低于阈值",
                    rejected_edge=candidate,
                )

        unique: dict[tuple, Edge] = {}
        for edge in edges:
            unique[(edge.src_type, edge.src_id, edge.dst_type, edge.dst_id, edge.relation)] = edge

        return EntryExtraction(
            entry_id=entry_id,
            entities=tuple(entities.values()),
            edges=tuple(unique.values()),
            rejected=tuple(rejected),
            n_components=len(match_entities("component", symptom_text)),
            n_metrics=len(match_entities("metric", symptom_text)),
            n_runs=len(match_entities("run", action_text)),
        )

    def extract_catalog(self, entries: Iterable[dict[str, Any]]) -> ExtractionResult:
        result = ExtractionResult()
        for entry in entries:
            extraction = self.extract_entry(entry)
            for entity in extraction.entities:
                result.entities[entity.key] = entity
            result.edges.extend(extraction.edges)
            result.rejected.extend(extraction.rejected)
            result.entry_stats[extraction.entry_id] = {
                "n_edges": len(extraction.edges),
                "n_rejected": len(extraction.rejected),
                "n_components": extraction.n_components,
                "n_metrics": extraction.n_metrics,
                "n_runs": extraction.n_runs,
            }
        return result


__all__ = [
    "RuleExtractor",
    "EntryExtraction",
    "parse_entry_payload",
    "CONF_SYMPTOM",
    "CONF_ACTION",
    "CONF_WEAK",
    "DEFAULT_MIN_CONFIDENCE",
]

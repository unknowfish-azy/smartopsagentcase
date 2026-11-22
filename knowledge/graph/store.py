"""图存储（P2-7 / B3）：进程内邻接表 + JSON 落盘。

方案口径：§3.2 非目标——**不引 Neo4j / 第三方图数据库**，
图用进程内邻接表 + JSON 落盘即可。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .schema import Edge, Entity, ExtractionResult


@dataclass
class KnowledgeGraph:
    """有向图：节点字典 + 邻接表（出边）+ 反向索引（入边）。"""

    nodes: dict[tuple[str, str], Entity] = field(default_factory=dict)
    out_edges: dict[tuple[str, str], list[Edge]] = field(default_factory=dict)
    in_edges: dict[tuple[str, str], list[Edge]] = field(default_factory=dict)
    edge_count: int = 0

    # ------------------------------------------------------------------
    # 构建
    # ------------------------------------------------------------------

    @classmethod
    def from_extraction(cls, result: ExtractionResult) -> "KnowledgeGraph":
        graph = cls()
        for entity in result.entities.values():
            graph.add_node(entity)
        for edge in result.edges:
            graph.add_edge(edge)
        return graph

    def add_node(self, entity: Entity) -> None:
        self.nodes[entity.key] = entity
        self.out_edges.setdefault(entity.key, [])
        self.in_edges.setdefault(entity.key, [])

    def add_edge(self, edge: Edge) -> None:
        if edge.src_key not in self.nodes:
            self.add_node(Entity(edge.src_type, edge.src_id, edge.src_id))
        if edge.dst_key not in self.nodes:
            self.add_node(Entity(edge.dst_type, edge.dst_id, edge.dst_id))
        self.out_edges.setdefault(edge.src_key, []).append(edge)
        self.in_edges.setdefault(edge.dst_key, []).append(edge)
        self.edge_count += 1

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def neighbors(
        self,
        key: tuple[str, str],
        *,
        relation: str | None = None,
        direction: str = "out",
    ) -> list[Edge]:
        """出入边；``relation`` 给定则只返回该关系类型。"""

        if direction == "out":
            edges = self.out_edges.get(key, [])
        elif direction == "in":
            edges = self.in_edges.get(key, [])
        else:
            raise ValueError("direction 只能是 out / in")
        if relation is None:
            return list(edges)
        return [edge for edge in edges if edge.relation == relation]

    def has_relation(self, src: tuple[str, str], dst: tuple[str, str], relation: str) -> bool:
        return any(
            edge.dst_key == dst and edge.relation == relation
            for edge in self.out_edges.get(src, [])
        )

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        edges: list[dict] = []
        for bucket in self.out_edges.values():
            edges.extend(edge.to_dict() for edge in bucket)
        return {
            "n_nodes": len(self.nodes),
            "n_edges": self.edge_count,
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "edges": edges,
        }

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return target

    @classmethod
    def load(cls, path: str | Path) -> "KnowledgeGraph":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        graph = cls()
        for node in payload.get("nodes") or []:
            graph.add_node(Entity(node["type"], node["id"], node.get("label", "")))
        for edge in payload.get("edges") or []:
            graph.add_edge(Edge(
                src_type=edge["src_type"], src_id=edge["src_id"],
                dst_type=edge["dst_type"], dst_id=edge["dst_id"],
                relation=edge["relation"], confidence=float(edge["confidence"]),
                source_entry_id=edge["source_entry_id"],
                extractor=edge.get("extractor", ""),
                evidence_text=edge.get("evidence_text", ""),
            ))
        return graph


__all__ = ["KnowledgeGraph"]

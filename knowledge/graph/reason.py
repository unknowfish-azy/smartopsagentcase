"""符号推理机（P2-7 / B4）。

方案口径：`docs/design/p2-7-causal-kg-debate-v1/DESIGN.md` §3.3。

推导规则（纯 Python 符号规则，可解释）
----------------------------------

    给定 alert A：
      candidates = { C | (A)-caused_by->(C) }           ← 硬约束：必须有 caused_by 边
      沿 depends_on **反向**扩展 1~2 跳（谁依赖这个组件）
      沿 emits 正向扩展（同服务的其它告警）
      按「路径条数 + 边置信度」排序
      输出：候选列表 + 每条候选的**推导路径**（可回溯到 source_entry_id）

**硬约束**：没有 `caused_by` 边的告警**不得**产出符号候选。
此时 ``status="neural_only"``——召回可以交给神经侧（hybrid），
但**禁止**把结果写成「符号推理得出」（方案 §5 第 7 条）。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .schema import Edge
from .store import KnowledgeGraph

# (关系, 方向)；方向 in 表示沿入边反向走
TRANSITIONS: tuple[tuple[str, str], ...] = (
    ("caused_by", "out"),
    ("depends_on", "in"),
    ("emits", "out"),
)

CANDIDATE_TYPES: tuple[str, ...] = ("component", "metric", "service")


@dataclass(frozen=True)
class DerivationStep:
    """一步推导：可回溯到 ``source_entry_id``。"""

    relation: str
    src_type: str
    src_id: str
    dst_type: str
    dst_id: str
    confidence: float
    source_entry_id: str

    @classmethod
    def from_edge(cls, edge: Edge, *, reverse: bool = False) -> "DerivationStep":
        return cls(
            relation=edge.relation,
            src_type=edge.dst_type if reverse else edge.src_type,
            src_id=edge.dst_id if reverse else edge.src_id,
            dst_type=edge.src_type if reverse else edge.dst_type,
            dst_id=edge.src_id if reverse else edge.dst_id,
            confidence=edge.confidence,
            source_entry_id=edge.source_entry_id,
        )

    def explain(self) -> str:
        return (
            f"{self.src_type}:{self.src_id} "
            f"--[{self.relation}|conf={self.confidence:.2f}"
            f"|src={self.source_entry_id}]--> "
            f"{self.dst_type}:{self.dst_id}"
        )


@dataclass(frozen=True)
class Candidate:
    """一个候选根因（组件 / 指标 / 服务）及其全部推导路径。"""

    key: tuple[str, str]
    score: float
    n_paths: int
    paths: tuple[tuple[DerivationStep, ...], ...] = field(compare=False)

    def explain(self, limit: int = 3) -> str:
        lines = [f"候选 {self.key[0]}:{self.key[1]}（score={self.score:.3f}，{self.n_paths} 条路径）"]
        for path in self.paths[:limit]:
            lines.append("  " + " → ".join(step.explain() for step in path))
        if self.n_paths > limit:
            lines.append(f"  …另有 {self.n_paths - limit} 条路径")
        return "\n".join(lines)


@dataclass(frozen=True)
class ReasoningResult:
    alert_id: str
    status: str            # "derived" | "neural_only" | "no_candidate"
    candidates: tuple[Candidate, ...]
    visited_nodes: int
    reason: str

    def to_dict(self) -> dict:
        return {
            "alert_id": self.alert_id,
            "status": self.status,
            "candidates": [
                {
                    "type": candidate.key[0],
                    "id": candidate.key[1],
                    "score": round(candidate.score, 6),
                    "n_paths": candidate.n_paths,
                    "paths": [
                        [step.explain() for step in path] for path in candidate.paths
                    ],
                }
                for candidate in self.candidates
            ],
            "visited_nodes": self.visited_nodes,
            "reason": self.reason,
        }


class SymbolicReasoner:
    """符号推理机：只吃 ``KnowledgeGraph``，不做任何检索 / 模型调用。"""

    def __init__(self, graph: KnowledgeGraph, max_hops: int = 2) -> None:
        if max_hops < 1:
            raise ValueError("max_hops 至少为 1")
        self.graph = graph
        self.max_hops = max_hops

    def candidates_for_alert(self, alert_id: str) -> ReasoningResult:
        start = ("alert", alert_id)
        if start not in self.graph.nodes:
            return ReasoningResult(
                alert_id=alert_id, status="no_candidate", candidates=(),
                visited_nodes=0, reason=f"图里没有告警节点 {alert_id}",
            )

        # 硬约束：必须有 caused_by 出边，否则不得产出符号候选
        direct = self.graph.neighbors(start, relation="caused_by")
        if not direct:
            has_emits = bool(self.graph.neighbors(start, relation="emits", direction="in"))
            return ReasoningResult(
                alert_id=alert_id,
                status="neural_only" if has_emits else "no_candidate",
                candidates=(),
                visited_nodes=1,
                reason=(
                    "该告警没有 caused_by 边（词表未覆盖其症状文本）→ 只做召回，不做符号结论"
                    if has_emits else "该告警在图里没有任何出边"
                ),
            )

        paths_by_candidate: dict[tuple[str, str], list[tuple[DerivationStep, ...]]] = {}
        queue: deque[tuple[tuple[str, str], tuple[DerivationStep, ...]]] = deque()
        visited: set[tuple[str, str]] = {start}

        for edge in direct:
            step = DerivationStep.from_edge(edge)
            queue.append((edge.dst_key, (step,)))

        while queue:
            node, path = queue.popleft()
            if node[0] in CANDIDATE_TYPES:
                paths_by_candidate.setdefault(node, []).append(path)
            if len(path) >= self.max_hops:
                continue
            for relation, direction in TRANSITIONS:
                reverse = direction == "in"
                for edge in self.graph.neighbors(node, relation=relation, direction=direction):
                    nxt = edge.src_key if reverse else edge.dst_key
                    if nxt in visited:
                        continue
                    visited.add(nxt)
                    queue.append((nxt, path + (DerivationStep.from_edge(edge, reverse=reverse),)))

        if not paths_by_candidate:
            return ReasoningResult(
                alert_id=alert_id, status="derived", candidates=(),
                visited_nodes=len(visited),
                reason="有 caused_by 边但没有落到候选类型节点",
            )

        candidates = [
            Candidate(
                key=key,
                score=round(len(paths) * 0.5 + _mean_confidence(paths), 6),
                n_paths=len(paths),
                paths=tuple(paths),
            )
            for key, paths in paths_by_candidate.items()
        ]
        candidates.sort(key=lambda c: (-c.score, -c.n_paths, c.key))

        return ReasoningResult(
            alert_id=alert_id,
            status="derived",
            candidates=tuple(candidates),
            visited_nodes=len(visited),
            reason=(
                f"沿 caused_by + depends_on(反向) + emits 扩展 ≤{self.max_hops} 跳，"
                f"得 {len(candidates)} 个候选"
            ),
        )


def _mean_confidence(paths: list[tuple[DerivationStep, ...]]) -> float:
    total = sum(step.confidence for path in paths for step in path)
    count = sum(len(path) for path in paths)
    return total / count if count else 0.0


__all__ = [
    "TRANSITIONS",
    "CANDIDATE_TYPES",
    "DerivationStep",
    "Candidate",
    "ReasoningResult",
    "SymbolicReasoner",
]

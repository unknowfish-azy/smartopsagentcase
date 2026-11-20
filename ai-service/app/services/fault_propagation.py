"""P2-3 故障传播推演服务。

基于服务拓扑（DAG）+ 加权 BFS 模拟故障扩散路径：
- 输入：拓扑边（含传播权重）、当前异常节点、推演深度
- 输出：未来 N 跳内可能受影响的服务列表、传播路径、影响范围评估

设计原则：
- 确定性算法：BFS + 加权扩散，不依赖 LLM，永远可用；
- 权重来源：可来自 knowledge_prior 的先验规则，也可由用户自定义；
- 不伪造：输出是"可能受影响"的概率估计，不是确定性预测；
- 支持双向推演：正向（下游影响）+ 反向（上游根因候选）。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Literal

from .knowledge_prior import PriorRule, BUILTIN_RULES


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class TopologyEdge:
    """拓扑边：source → target，带传播权重。"""
    source: str
    target: str
    weight: float = 0.5  # 传播概率 0-1
    relation: str = "depends_on"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "weight": self.weight,
            "relation": self.relation,
        }


@dataclass
class PropagationNode:
    """推演过程中的一个节点状态。"""
    node_id: str
    depth: int                    # 距源节点的跳数
    probability: float            # 被波及的概率（路径权重累乘）
    path: list[str] = field(default_factory=list)  # 传播路径

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "depth": self.depth,
            "probability": round(self.probability, 4),
            "path": self.path,
        }


@dataclass
class PropagationResult:
    """推演结果。"""
    source: str
    direction: Literal["forward", "backward"]
    affected: list[PropagationNode]
    max_depth: int
    total_affected: int
    high_risk_count: int  # probability > 0.5 的节点数

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "direction": self.direction,
            "affected": [n.to_dict() for n in self.affected],
            "max_depth": self.max_depth,
            "total_affected": self.total_affected,
            "high_risk_count": self.high_risk_count,
        }


# ---------------------------------------------------------------------------
# 推演引擎
# ---------------------------------------------------------------------------

def propagate(
    source: str,
    edges: list[TopologyEdge],
    max_depth: int = 3,
    min_probability: float = 0.05,
    direction: Literal["forward", "backward"] = "forward",
) -> PropagationResult:
    """加权 BFS 推演故障传播。

    Args:
        source: 故障源节点
        edges: 拓扑边列表
        max_depth: 最大推演深度（跳数）
        min_probability: 概率阈值，低于此值的节点不纳入结果
        direction: forward=下游影响，backward=上游根因候选

    Returns:
        PropagationResult
    """
    # 构建邻接表
    adj: dict[str, list[TopologyEdge]] = {}
    for edge in edges:
        if direction == "forward":
            adj.setdefault(edge.source, []).append(edge)
        else:
            # 反向：从 target 找 source
            reversed_edge = TopologyEdge(edge.target, edge.source, edge.weight, edge.relation)
            adj.setdefault(edge.target, []).append(reversed_edge)

    visited: dict[str, PropagationNode] = {}
    queue: deque[PropagationNode] = deque()

    root = PropagationNode(source, 0, 1.0, [source])
    queue.append(root)
    visited[source] = root

    while queue:
        current = queue.popleft()
        if current.depth >= max_depth:
            continue

        for edge in adj.get(current.node_id, []):
            # 反向时边已被 reverse，统一用 target
            next_id = edge.target
            # 防止回环：不回到路径中已有的节点
            if next_id in current.path:
                continue
            prob = current.probability * edge.weight
            if prob < min_probability:
                continue

            existing = visited.get(next_id)
            if existing is not None and existing.probability >= prob:
                continue

            node = PropagationNode(
                next_id, current.depth + 1, prob,
                current.path + [next_id],
            )
            visited[next_id] = node
            queue.append(node)

    # 排除源节点自身
    affected = [n for nid, n in visited.items() if nid != source]
    affected.sort(key=lambda n: (-n.probability, n.depth))

    return PropagationResult(
        source=source,
        direction=direction,
        affected=affected,
        max_depth=max((n.depth for n in affected), default=0),
        total_affected=len(affected),
        high_risk_count=sum(1 for n in affected if n.probability > 0.5),
    )


def assess_impact(
    source: str,
    edges: list[TopologyEdge],
    critical_services: set[str] | None = None,
    max_depth: int = 3,
) -> dict[str, Any]:
    """评估故障影响范围（正向推演 + 关键服务命中分析）。

    Args:
        source: 故障源节点
        edges: 拓扑边
        critical_services: 关键服务集合，命中则提升风险等级
        max_depth: 推演深度

    Returns:
        {
            "propagation": PropagationResult.to_dict(),
            "risk_level": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
            "critical_hit": list[str],   # 被波及的关键服务
            "recommendation": str,       # 处置建议
        }
    """
    result = propagate(source, edges, max_depth=max_depth, direction="forward")

    critical_hit: list[str] = []
    if critical_services:
        critical_hit = [
            n.node_id for n in result.affected
            if n.node_id in critical_services
        ]

    # 风险等级判定
    if critical_hit and result.high_risk_count >= 2:
        risk_level = "CRITICAL"
        recommendation = f"立即处置：{source} 故障将波及 {len(critical_hit)} 个关键服务，建议优先隔离"
    elif critical_hit or result.high_risk_count >= 3:
        risk_level = "HIGH"
        recommendation = f"高优先级：{source} 故障影响范围较大，建议 15 分钟内处置"
    elif result.total_affected >= 2:
        risk_level = "MEDIUM"
        recommendation = f"中优先级：{source} 故障可能波及 {result.total_affected} 个服务，建议关注"
    else:
        risk_level = "LOW"
        recommendation = f"低优先级：{source} 故障影响有限，可按常规流程处置"

    return {
        "propagation": result.to_dict(),
        "risk_level": risk_level,
        "critical_hit": critical_hit,
        "recommendation": recommendation,
    }


# ---------------------------------------------------------------------------
# 从先验规则构建拓扑
# ---------------------------------------------------------------------------

def edges_from_priors(rules: list[PriorRule] | None = None) -> list[TopologyEdge]:
    """把 knowledge_prior 的规则转换为拓扑边。"""
    if rules is None:
        rules = BUILTIN_RULES
    return [
        TopologyEdge(r.source, r.target, r.weight, r.relation)
        for r in rules
    ]


def find_root_cause_candidates(
    symptom_node: str,
    edges: list[TopologyEdge],
    max_depth: int = 3,
) -> list[PropagationNode]:
    """反向推演：从症状节点找可能的根因。

    返回按概率降序的根因候选列表。
    """
    result = propagate(symptom_node, edges, max_depth=max_depth, direction="backward")
    return result.affected


def get_model_info() -> dict[str, Any]:
    return {
        "available": True,
        "kind": "weighted_bfs",
        "reason": "确定性图算法，零依赖，永远可用",
        "builtin_edges": len(BUILTIN_RULES),
        "max_depth_default": 3,
        "directions": ["forward", "backward"],
    }

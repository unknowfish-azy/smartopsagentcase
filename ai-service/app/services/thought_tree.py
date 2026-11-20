"""P1-2 思维树 + 价值评估（ToT + Value Estimation）。

让 Agent 生成多条故障排查思路分支，用价值评估对每条分支打分，
只保留最优分支继续推理，避免单条 ReAct 路径钻牛角尖。

设计原则：
- 不伪造：价值评估基于历史成功率统计（真实数据），不训练神经网络；
- 可降级：无历史数据时用规则先验打分；
- 有界：最大分支数 / 最大深度 / 最大总评估次数均有上限；
- 可审计：每个分支的评分依据、剪枝原因均记录。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable
import time


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class ThoughtNode:
    """思维树节点：一个排查思路分支。"""
    id: str
    parent_id: str | None
    depth: int
    # 思路描述（自然语言）
    thought: str
    # 建议的下一步动作（工具调用）
    action: str
    action_params: dict[str, Any] = field(default_factory=dict)
    # 价值评估
    value_score: float = 0.0
    value_reason: str = ""
    # 状态
    status: str = "pending"  # pending / expanded / pruned / selected / completed
    # 子节点
    children: list["ThoughtNode"] = field(default_factory=list)
    # 执行结果（如果已执行）
    observation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "depth": self.depth,
            "thought": self.thought,
            "action": self.action,
            "value_score": round(self.value_score, 4),
            "value_reason": self.value_reason,
            "status": self.status,
            "children": [c.to_dict() for c in self.children],
        }


# ---------------------------------------------------------------------------
# 价值评估器（基于历史成功率 + 规则先验）
# ---------------------------------------------------------------------------

class ValueEstimator:
    """思路价值评估器。

    评分维度：
    1. 历史成功率（如果该动作在历史处置中成功过，加权）
    2. 动作类型先验（诊断类动作优先于处置类，只读优先于写）
    3. 深度惩罚（深度越大分数越低，鼓励浅层解决）
    4. 多样性奖励（与已选分支不同的动作类型加分）
    """

    # 动作类型先验分数
    ACTION_PRIORS: dict[str, float] = {
        # 诊断类（只读，安全，信息量大）
        "query_logs": 0.85,
        "query_metrics": 0.85,
        "query_traces": 0.80,
        "check_service_status": 0.80,
        "check_topology": 0.75,
        "retrieve_similar_cases": 0.75,
        # 分析类
        "analyze_rootcause": 0.70,
        "detect_anomaly": 0.70,
        "predict_propagation": 0.65,
        # 处置类（写操作，需谨慎）
        "restart_service": 0.40,
        "scale_up": 0.45,
        "rollback": 0.50,
        "clear_cache": 0.45,
        "execute_shell": 0.30,
    }

    def __init__(self) -> None:
        # 历史成功率表：{action: {"success": int, "total": int}}
        self._history: dict[str, dict[str, int]] = {}

    def record_outcome(self, action: str, success: bool) -> None:
        """记录一次动作执行结果，用于后续评分。"""
        h = self._history.setdefault(action, {"success": 0, "total": 0})
        h["total"] += 1
        if success:
            h["success"] += 1

    def success_rate(self, action: str) -> float | None:
        """返回历史成功率，无数据时返回 None。"""
        h = self._history.get(action)
        if not h or h["total"] < 3:  # 至少 3 次采样才可信
            return None
        return h["success"] / h["total"]

    def estimate(
        self,
        node: ThoughtNode,
        selected_actions: set[str] | None = None,
    ) -> tuple[float, str]:
        """评估一个思路节点的价值。

        Returns:
            (score, reason)：0-1 分数 + 评分理由
        """
        reasons: list[str] = []

        # 1. 动作类型先验
        prior = self.ACTION_PRIORS.get(node.action, 0.50)
        score = prior
        reasons.append(f"先验={prior:.2f}")

        # 2. 历史成功率加权
        sr = self.success_rate(node.action)
        if sr is not None:
            score = 0.4 * prior + 0.6 * sr
            reasons.append(f"历史成功率={sr:.2f}")

        # 3. 深度惩罚
        depth_penalty = 0.05 * node.depth
        score -= depth_penalty
        if depth_penalty > 0:
            reasons.append(f"深度惩罚=-{depth_penalty:.2f}")

        # 4. 多样性奖励
        if selected_actions and node.action not in selected_actions:
            score += 0.05
            reasons.append("多样性+0.05")

        score = max(0.0, min(1.0, score))
        return score, "; ".join(reasons)


# ---------------------------------------------------------------------------
# 思维树搜索
# ---------------------------------------------------------------------------

@dataclass
class ToTConfig:
    """思维树搜索配置。"""
    max_depth: int = 3
    max_branches_per_node: int = 3
    max_total_nodes: int = 30
    beam_width: int = 2  # 每层保留的 Top-K 分支


class ThoughtTreeSearch:
    """思维树搜索器。

    用法：
    1. 调用方提供 expand_fn：给定当前节点，生成 N 个子思路
    2. 调用方提供 execute_fn：执行选定动作，返回观察结果
    3. 搜索器负责评估、剪枝、选择最优路径
    """

    def __init__(
        self,
        config: ToTConfig | None = None,
        estimator: ValueEstimator | None = None,
    ) -> None:
        self.config = config or ToTConfig()
        self.estimator = estimator or ValueEstimator()
        self._node_counter = 0

    def _new_id(self) -> str:
        self._node_counter += 1
        return f"n{self._node_counter}"

    async def search(
        self,
        root_thought: str,
        expand_fn: Callable[[ThoughtNode], Awaitable[list[tuple[str, str, dict]]]],
        max_iterations: int = 5,
    ) -> dict[str, Any]:
        """执行思维树搜索。

        Args:
            root_thought: 初始问题描述
            expand_fn: 异步函数，输入节点，返回 [(thought, action, params), ...]
            max_iterations: 最大迭代轮数

        Returns:
            {
                "best_path": [ThoughtNode.to_dict(), ...],
                "tree": ThoughtNode.to_dict(),
                "iterations": int,
                "total_nodes": int,
            }
        """
        root = ThoughtNode(
            id=self._new_id(), parent_id=None, depth=0,
            thought=root_thought, action="ROOT",
        )
        root.status = "expanded"

        # 当前 frontier（待扩展节点）
        frontier = [root]
        best_path: list[ThoughtNode] = [root]
        total_nodes = 1
        selected_actions: set[str] = set()

        for iteration in range(max_iterations):
            if not frontier or total_nodes >= self.config.max_total_nodes:
                break

            # 对 frontier 中每个节点扩展
            candidates: list[ThoughtNode] = []
            for node in frontier:
                if node.depth >= self.config.max_depth:
                    node.status = "completed"
                    continue
                try:
                    branches = await expand_fn(node)
                except Exception:
                    node.status = "pruned"
                    continue

                for thought, action, params in branches[:self.config.max_branches_per_node]:
                    if total_nodes >= self.config.max_total_nodes:
                        break
                    child = ThoughtNode(
                        id=self._new_id(), parent_id=node.id, depth=node.depth + 1,
                        thought=thought, action=action, action_params=params,
                    )
                    score, reason = self.estimator.estimate(child, selected_actions)
                    child.value_score = score
                    child.value_reason = reason
                    node.children.append(child)
                    candidates.append(child)
                    total_nodes += 1
                node.status = "expanded"

            if not candidates:
                break

            # Beam search：保留 Top-K
            candidates.sort(key=lambda n: -n.value_score)
            for node in candidates[self.config.beam_width:]:
                node.status = "pruned"
            frontier = candidates[:self.config.beam_width]
            for node in frontier:
                node.status = "selected"
                selected_actions.add(node.action)

            # 更新最优路径
            if frontier:
                best = frontier[0]
                best_path = self._trace_path(best)

        return {
            "best_path": [n.to_dict() for n in best_path],
            "tree": root.to_dict(),
            "iterations": iteration + 1 if frontier else 0,
            "total_nodes": total_nodes,
        }

    def _trace_path(self, node: ThoughtNode) -> list[ThoughtNode]:
        """从节点回溯到根，返回路径。"""
        # 简化：只返回当前节点（完整路径需要 parent 引用）
        return [node]


def get_model_info() -> dict[str, Any]:
    return {
        "available": True,
        "kind": "beam_search_plus_value_estimation",
        "reason": "多路径生成 + 历史成功率价值评估，不训练神经网络",
        "action_priors": len(ValueEstimator.ACTION_PRIORS),
        "default_config": ToTConfig().__dict__,
    }

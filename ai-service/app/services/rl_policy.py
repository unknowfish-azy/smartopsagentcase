"""P2-2 强化学习处置策略优化（Tabular Q-Learning）。

以"故障恢复时间、处置成功率、次生风险"为奖励函数，
用 Q-Learning 训练 Agent 的处置策略，优化排查顺序与动作选择。

设计原则：
- 真实 RL：标准 Q-Learning 算法（Watkins 1989），不是规则伪装的；
- 轻量：Tabular Q-Learning 不需要 GPU，状态用离散特征编码；
- 安全：Q 表只推荐动作，最终决策权在 Kimi + 风险门；
- 可解释：每个 Q 值可追溯到具体的 (状态, 动作) 历史奖励；
- 可降级：Q 表为空时用 ε-greedy 探索，不会卡死。
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Literal


# ---------------------------------------------------------------------------
# 状态编码
# ---------------------------------------------------------------------------

@dataclass
class DiagnosisState:
    """诊断状态：用于 Q-Learning 的状态表示。

    用离散特征编码，便于 Tabular Q-Learning。
    """
    # 异常类型：cpu / memory / disk / network / db / cache / unknown
    anomaly_type: str = "unknown"
    # 严重度：low / medium / high / critical
    severity: str = "medium"
    # 是否已有根因候选
    has_rootcause: bool = False
    # 已执行的诊断步数（离散化：0 / 1-2 / 3-5 / 6+）
    step_bucket: Literal["0", "1-2", "3-5", "6+"] = "0"
    # 是否有历史相似案例
    has_similar_case: bool = False

    def to_key(self) -> str:
        """编码为 Q 表的状态键。"""
        return (
            f"{self.anomaly_type}|{self.severity}|"
            f"rc={int(self.has_rootcause)}|step={self.step_bucket}|"
            f"case={int(self.has_similar_case)}"
        )

    @staticmethod
    def from_steps(
        anomaly_type: str,
        severity: str,
        has_rootcause: bool,
        step_count: int,
        has_similar_case: bool,
    ) -> "DiagnosisState":
        if step_count == 0:
            bucket = "0"
        elif step_count <= 2:
            bucket = "1-2"
        elif step_count <= 5:
            bucket = "3-5"
        else:
            bucket = "6+"
        return DiagnosisState(anomaly_type, severity, has_rootcause, bucket, has_similar_case)


# ---------------------------------------------------------------------------
# 奖励计算
# ---------------------------------------------------------------------------

def compute_reward(
    action: str,
    outcome: Literal["success", "partial", "failure", "side_effect"],
    time_cost_seconds: float,
    is_final_action: bool = False,
) -> float:
    """计算一次动作的即时奖励。

    奖励设计：
    - 成功处置：+1.0（终止奖励 +2.0）
    - 部分成功：+0.3
    - 失败：-0.5
    - 次生风险：-2.0（强惩罚）
    - 时间成本：每秒 -0.001（鼓励快速处置）
    - 终止动作额外奖励/惩罚
    """
    base_reward = {
        "success": 1.0,
        "partial": 0.3,
        "failure": -0.5,
        "side_effect": -2.0,
    }[outcome]

    # 时间惩罚
    time_penalty = -0.001 * min(time_cost_seconds, 300)  # 上限 5 分钟

    # 终止奖励
    terminal_bonus = 0.0
    if is_final_action:
        if outcome == "success":
            terminal_bonus = 2.0
        elif outcome == "failure":
            terminal_bonus = -1.0

    return base_reward + time_penalty + terminal_bonus


# ---------------------------------------------------------------------------
# Q-Learning 策略
# ---------------------------------------------------------------------------

@dataclass
class QEntry:
    """Q 表条目。"""
    q_value: float = 0.0
    visit_count: int = 0
    last_reward: float = 0.0
    last_updated: float = field(default_factory=time.time)


class QLearningPolicy:
    """Tabular Q-Learning 处置策略。

    标准 Q-Learning 更新规则：
        Q(s,a) ← Q(s,a) + α * [r + γ * max_a' Q(s',a') - Q(s,a)]
    """

    # 可选动作集
    ACTIONS: list[str] = [
        "query_logs",
        "query_metrics",
        "query_traces",
        "retrieve_similar_cases",
        "analyze_rootcause",
        "detect_anomaly",
        "predict_propagation",
        "restart_service",
        "rollback",
        "clear_cache",
        "escalate_to_human",
    ]

    def __init__(
        self,
        learning_rate: float = 0.1,
        discount: float = 0.95,
        epsilon: float = 0.1,
    ) -> None:
        """
        Args:
            learning_rate: 学习率 α
            discount: 折扣因子 γ
            epsilon: 探索率 ε（ε-greedy）
        """
        self.alpha = learning_rate
        self.gamma = discount
        self.epsilon = epsilon
        # Q 表：{state_key: {action: QEntry}}
        self._q_table: dict[str, dict[str, QEntry]] = {}

    def _get_entry(self, state_key: str, action: str) -> QEntry:
        if state_key not in self._q_table:
            self._q_table[state_key] = {}
        if action not in self._q_table[state_key]:
            self._q_table[state_key][action] = QEntry()
        return self._q_table[state_key][action]

    def select_action(
        self,
        state: DiagnosisState,
        allowed_actions: list[str] | None = None,
        explore: bool = True,
    ) -> tuple[str, str]:
        """ε-greedy 选择动作。

        Args:
            state: 当前状态
            allowed_actions: 允许的动作集（安全约束），None 表示全部
            explore: 是否启用探索（推理时通常关闭）

        Returns:
            (action, reason)：选中的动作 + 选择理由
        """
        actions = allowed_actions or self.ACTIONS
        state_key = state.to_key()

        # ε-greedy 探索
        if explore and random.random() < self.epsilon:
            action = random.choice(actions)
            return action, f"ε-greedy 探索 (ε={self.epsilon})"

        # 利用：选 Q 值最高的
        q_values = {a: self._get_entry(state_key, a).q_value for a in actions}
        best_action = max(q_values, key=q_values.get)  # type: ignore[arg-type]
        best_q = q_values[best_action]

        if best_q == 0.0:
            # 无历史数据时，优先诊断类动作
            for a in ["query_logs", "query_metrics", "retrieve_similar_cases"]:
                if a in actions:
                    return a, "无历史数据，优先诊断"

        return best_action, f"Q 值最高 (Q={best_q:.3f})"

    def update(
        self,
        state: DiagnosisState,
        action: str,
        reward: float,
        next_state: DiagnosisState | None,
    ) -> float:
        """Q-Learning 更新。

        Args:
            state: 执行前状态
            action: 执行的动作
            reward: 即时奖励
            next_state: 执行后状态，None 表示终止

        Returns:
            更新后的 Q 值
        """
        state_key = state.to_key()
        entry = self._get_entry(state_key, action)

        # 计算目标值
        if next_state is None:
            target = reward
        else:
            next_key = next_state.to_key()
            next_q_values = [
                self._get_entry(next_key, a).q_value for a in self.ACTIONS
            ]
            target = reward + self.gamma * max(next_q_values)

        # Q-Learning 更新
        new_q = entry.q_value + self.alpha * (target - entry.q_value)
        entry.q_value = new_q
        entry.visit_count += 1
        entry.last_reward = reward
        entry.last_updated = time.time()

        return new_q

    def get_q_table_snapshot(self, state: DiagnosisState) -> dict[str, float]:
        """获取某状态下所有动作的 Q 值快照（可解释性）。"""
        state_key = state.to_key()
        if state_key not in self._q_table:
            return {}
        return {a: e.q_value for a, e in self._q_table[state_key].items()}

    def export_q_table(self) -> dict[str, dict[str, float]]:
        """导出完整 Q 表（用于持久化）。"""
        return {
            sk: {a: e.q_value for a, e in actions.items()}
            for sk, actions in self._q_table.items()
        }

    def import_q_table(self, data: dict[str, dict[str, float]]) -> None:
        """导入 Q 表（用于恢复）。"""
        self._q_table = {}
        for sk, actions in data.items():
            self._q_table[sk] = {}
            for a, q in actions.items():
                self._q_table[sk][a] = QEntry(q_value=q)


# ---------------------------------------------------------------------------
# 轨迹记录
# ---------------------------------------------------------------------------

@dataclass
class Trajectory:
    """一次完整处置的轨迹。"""
    episode_id: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    total_reward: float = 0.0
    final_outcome: str | None = None

    def add_step(
        self,
        state: DiagnosisState,
        action: str,
        reward: float,
        next_state: DiagnosisState | None,
    ) -> None:
        self.steps.append({
            "state": state.to_key(),
            "action": action,
            "reward": reward,
            "next_state": next_state.to_key() if next_state else None,
        })
        self.total_reward += reward


class RLPolicyService:
    """强化学习策略服务：组合 Q-Learning + 轨迹记录 + 奖励计算。"""

    def __init__(self) -> None:
        self.policy = QLearningPolicy()
        self._trajectories: list[Trajectory] = []
        self._episode_counter = 0

    def recommend(
        self,
        anomaly_type: str,
        severity: str,
        has_rootcause: bool,
        step_count: int,
        has_similar_case: bool,
        allowed_actions: list[str] | None = None,
    ) -> dict[str, Any]:
        """推荐下一步动作。"""
        state = DiagnosisState.from_steps(
            anomaly_type, severity, has_rootcause, step_count, has_similar_case,
        )
        action, reason = self.policy.select_action(state, allowed_actions, explore=False)
        q_snapshot = self.policy.get_q_table_snapshot(state)
        return {
            "recommended_action": action,
            "reason": reason,
            "q_values": q_snapshot,
            "state_key": state.to_key(),
        }

    def record_step(
        self,
        episode_id: str,
        anomaly_type: str,
        severity: str,
        has_rootcause: bool,
        step_count: int,
        has_similar_case: bool,
        action: str,
        outcome: Literal["success", "partial", "failure", "side_effect"],
        time_cost_seconds: float,
        is_final: bool = False,
    ) -> dict[str, Any]:
        """记录一步执行结果并更新 Q 表。"""
        state = DiagnosisState.from_steps(
            anomaly_type, severity, has_rootcause, step_count, has_similar_case,
        )
        next_state = None if is_final else DiagnosisState.from_steps(
            anomaly_type, severity, has_rootcause, step_count + 1, has_similar_case,
        )

        reward = compute_reward(action, outcome, time_cost_seconds, is_final)
        new_q = self.policy.update(state, action, reward, next_state)

        # 记录轨迹
        traj = next((t for t in self._trajectories if t.episode_id == episode_id), None)
        if traj is None:
            traj = Trajectory(episode_id)
            self._trajectories.append(traj)
        traj.add_step(state, action, reward, next_state)
        if is_final:
            traj.final_outcome = outcome

        return {
            "reward": round(reward, 4),
            "new_q_value": round(new_q, 4),
            "episode_total_reward": round(traj.total_reward, 4),
        }

    def get_stats(self) -> dict[str, Any]:
        return {
            "q_table_size": len(self.policy._q_table),
            "total_episodes": len(self._trajectories),
            "total_steps": sum(len(t.steps) for t in self._trajectories),
            "avg_reward": (
                sum(t.total_reward for t in self._trajectories) / len(self._trajectories)
                if self._trajectories else 0.0
            ),
        }


def get_model_info() -> dict[str, Any]:
    return {
        "available": True,
        "kind": "tabular_q_learning",
        "reason": "标准 Q-Learning，真实 RL 算法，不需要 GPU",
        "actions": len(QLearningPolicy.ACTIONS),
        "reference": "Watkins 1989",
    }

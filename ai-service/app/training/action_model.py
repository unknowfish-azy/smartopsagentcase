"""P2-1 处置动作效果预测：共享模型。

任务：给定（故障 category, severity, 建议动作）→ 预测两个输出：
  1. success_prob      — 这个动作能解决问题的概率（越高越推荐执行）
  2. secondary_risk_prob — 这个动作会引发次生故障的概率（越低越安全）

两个输出组合成一个综合 risk_score：
  risk = (1 - success_prob) + secondary_risk_prob

数据源对齐 agent_decision_loop：
  - category     → 故障类别（oom/timeout/disk_full/...）
  - severity     → P0/P1/P2/P3
  - decision     → 处置动作（restart/scale_out/rollback/...）
  - outcome      → resolved/mitigated/failed（success 标签）
  - 次生故障     → outcome 是否产生额外事件（secondary_risk 标签，可弱标注）

模型结构：
  [故障特征 onehot concat 动作 onehot] → hidden → 双输出头
  故障特征 = category onehot(8) + severity ordinal(1) + metric context norm(1)
  动作特征 = action onehot(7)

依赖可选：torch → 双输出 MLP；无 torch → 规则启发式
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


# ---------------------------------------------------------------------------
# 标签空间（与 P1-3 的故障类别对齐）
# ---------------------------------------------------------------------------

CATEGORIES: tuple[str, ...] = (
    "oom", "timeout", "disk_full", "connection_refused",
    "process_crash", "auth_error", "network_error", "other",
)
NUM_CATEGORIES = len(CATEGORIES)
CATEGORY_TO_ID: dict[str, int] = {c: i for i, c in enumerate(CATEGORIES)}
ID_TO_CATEGORY: dict[int, str] = {i: c for i, c in enumerate(CATEGORIES)}

SEVERITIES = ["P0", "P1", "P2", "P3"]
SEVERITY_TO_IDX = {s: i for i, s in enumerate(SEVERITIES)}
SEVERITY_ORD = {s: float(len(SEVERITIES) - 1 - i) for i, s in enumerate(SEVERITIES)}  # P0=3, P3=0

ACTIONS: tuple[str, ...] = (
    "restart", "scale_out", "scale_in", "rollback",
    "config_change", "code_fix", "manual_cleanup", "wait_and_observe",
)
NUM_ACTIONS = len(ACTIONS)
ACTION_TO_ID: dict[str, int] = {a: i for i, a in enumerate(ACTIONS)}


# ---------------------------------------------------------------------------
# 依赖探测
# ---------------------------------------------------------------------------

_TORCH_AVAILABLE = False
try:
    import torch  # type: ignore[import-untyped]
    import torch.nn as nn  # type: ignore[import-untyped]
    _TORCH_AVAILABLE = True
except ImportError:
    torch = None
    nn = None


# ---------------------------------------------------------------------------
# 双任务 MLP
# ---------------------------------------------------------------------------

if _TORCH_AVAILABLE:

    class ActionEffectMLP(nn.Module):
        """双输出头 MLP：success_prob + secondary_risk_prob。"""

        def __init__(
            self,
            num_categories: int = NUM_CATEGORIES,
            num_actions: int = NUM_ACTIONS,
            hidden1: int = 32,
            hidden2: int = 16,
            dropout: float = 0.2,
        ):
            super().__init__()
            # 特征维度：category onehot(8) + severity_ordinal(1) + action onehot(8)
            feat_dim = num_categories + 1 + num_actions
            self.num_categories = num_categories
            self.num_actions = num_actions

            self.trunk = nn.Sequential(
                nn.Linear(feat_dim, hidden1),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(hidden1, hidden2),
                nn.ReLU(),
                nn.Dropout(dropout),
            )
            # 双输出头
            self.success_head = nn.Linear(hidden2, 1)
            self.risk_head = nn.Linear(hidden2, 1)

        def forward(self, x):
            h = self.trunk(x)
            success_logit = self.success_head(h).squeeze(-1)
            risk_logit = self.risk_head(h).squeeze(-1)
            return torch.sigmoid(success_logit), torch.sigmoid(risk_logit)


# ---------------------------------------------------------------------------
# 特征编码工具
# ---------------------------------------------------------------------------

def encode_features(
    category: str,
    severity: str,
    action: str,
    category_map: dict[str, int] | None = None,
    action_map: dict[str, int] | None = None,
) -> np.ndarray:
    """单条 → (feat_dim,) 特征向量。"""
    category_map = category_map or CATEGORY_TO_ID
    action_map = action_map or ACTION_TO_ID

    cat_onehot = np.zeros(NUM_CATEGORIES, dtype=np.float32)
    cat_idx = category_map.get(category, category_map.get("other", 0))
    cat_onehot[cat_idx] = 1.0

    sev_val = SEVERITY_ORD.get(severity, 1.5)  # 默认 P2

    act_onehot = np.zeros(NUM_ACTIONS, dtype=np.float32)
    act_idx = action_map.get(action, 0)
    act_onehot[act_idx] = 1.0

    return np.concatenate([cat_onehot, [sev_val], act_onehot]).astype(np.float32)


def encode_batch(
    categories: list[str],
    severities: list[str],
    actions: list[str],
) -> np.ndarray:
    """批量 → (N, feat_dim)。"""
    return np.stack([
        encode_features(c, s, a)
        for c, s, a in zip(categories, severities, actions)
    ])


# ---------------------------------------------------------------------------
# 启发式规则（无 torch 时的 fallback）
# ---------------------------------------------------------------------------

# 经验规则：哪些动作通常成功、哪些容易引发次生故障
_ACTION_SUCCESS_BASE: dict[str, float] = {
    "restart": 0.7, "scale_out": 0.75, "scale_in": 0.5,
    "rollback": 0.85, "config_change": 0.6, "code_fix": 0.9,
    "manual_cleanup": 0.8, "wait_and_observe": 0.5,
}
# 高风险动作（容易引发次生故障）
_ACTION_RISK_BASE: dict[str, float] = {
    "restart": 0.15, "scale_out": 0.05, "scale_in": 0.3,
    "rollback": 0.1, "config_change": 0.25, "code_fix": 0.0,
    "manual_cleanup": 0.1, "wait_and_observe": 0.05,
}
# 故障类别 × 动作 的交互效应（部分组合特别成功或特别危险）
_CATEGORY_ACTION_SUCCESS_DELTA: dict[tuple[str, str], float] = {
    ("oom", "scale_out"): 0.15, ("oom", "restart"): 0.1,
    ("timeout", "scale_out"): 0.1, ("timeout", "rollback"): 0.2,
    ("disk_full", "manual_cleanup"): 0.2, ("disk_full", "restart"): -0.1,
    ("process_crash", "restart"): 0.15, ("process_crash", "rollback"): 0.1,
    ("connection_refused", "restart"): 0.2, ("connection_refused", "wait_and_observe"): -0.1,
}


def heuristic_predict(category: str, severity: str, action: str) -> tuple[float, float, float]:
    """无 torch 时的规则预测 → (success, risk, risk_score)。"""
    base_s = _ACTION_SUCCESS_BASE.get(action, 0.6)
    base_r = _ACTION_RISK_BASE.get(action, 0.15)
    delta_s = _CATEGORY_ACTION_SUCCESS_DELTA.get((category, action), 0.0)
    success = max(0.0, min(1.0, base_s + delta_s))
    risk = max(0.0, min(1.0, base_r + (0.1 if severity in ("P0", "P1") else 0.0)))
    risk_score = max(0.0, min(1.0, (1.0 - success) + risk))
    return success, risk, risk_score


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

@dataclass
class ActionEffectConfig:
    epochs: int = 50
    batch_size: int = 32
    lr: float = 2e-3
    hidden1: int = 32
    hidden2: int = 16
    dropout: float = 0.2
    seed: int = 17


def available() -> str:
    return "mlp" if _TORCH_AVAILABLE else "heuristic"

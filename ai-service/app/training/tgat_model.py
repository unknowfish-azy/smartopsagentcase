"""P2 阶段 3：TGAT 动态拓扑根因模型。

与静态 RootCauseGAT 的区别：静态 GAT 假设拓扑固定（单快照），TGAT 输入**时间切片图序列**，
先用共享图编码器逐切片编码节点，再沿时间维用 GRU 聚合每个节点的演化，
适配 K8s 动态扩缩容下服务/实例上下线、故障沿调用链传播的场景。

骨架与 graph_model 一致：
- torch 可用 → TGATRootCause（纯 PyTorch，不依赖 PyG）
- torch 缺失/无权重 → heuristic（度+severity 逐切片打分 + 时间衰减 + 传播路径）

节点对齐：跨切片取节点并集，缺失切片该节点特征置 0 + mask 置 0（表示当时不在拓扑中）。
"""

from __future__ import annotations

import os
from typing import Any, Sequence

import numpy as np

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

_TORCH_AVAILABLE = False
try:
    import torch  # type: ignore[import-untyped]
    import torch.nn as nn  # type: ignore[import-untyped]
    import torch.nn.functional as F  # type: ignore[import-untyped]

    _TORCH_AVAILABLE = True
    try:
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
    except Exception:
        pass
except ImportError:  # pragma: no cover
    torch = None
    nn = None
    F = None


def available() -> str:
    return "tgat" if _TORCH_AVAILABLE else "heuristic"


NUM_NODE_FEATURES = 3  # severity_score, firing, degree_norm

_SEVERITY_SCORE = {"P0": 1.0, "P1": 0.75, "P2": 0.5, "P3": 0.25}


def _severity_score(value: Any) -> float:
    return _SEVERITY_SCORE.get(str(value or "P2").upper(), 0.5)


# 告警活跃状态：OPEN/PENDING_APPROVAL/REMEDIATING 视为 firing；CLOSED 视为已恢复。
_ACTIVE_STATUS = {"open", "pending_approval", "remediating", "firing"}


def _firing(node: dict[str, Any]) -> float:
    return 1.0 if str(node.get("status", "OPEN")).lower() in _ACTIVE_STATUS else 0.0


# ---------------------------------------------------------------------------
# 节点对齐 + 特征构造（训练推理共用）
# ---------------------------------------------------------------------------

def align_nodes(snapshots: Sequence[dict[str, Any]]) -> list[str]:
    """跨切片取节点并集，保持首次出现顺序（确定性）。"""
    seen: dict[str, None] = {}
    for snap in snapshots:
        for n in snap.get("nodes", []):
            seen.setdefault(n["alert_id"], None)
    return list(seen.keys())


def snapshot_features(snap: dict[str, Any], node_order: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """单切片 → (x[N,F], mask[N])，缺失节点特征 0、mask 0。"""
    idx = {nid: i for i, nid in enumerate(node_order)}
    n = len(node_order)
    nodes = snap.get("nodes", [])
    edges = snap.get("edges", [])

    degree = np.zeros(n, dtype=np.float32)
    for e in edges:
        a, b = e.get("alert_a_id"), e.get("alert_b_id")
        if a in idx:
            degree[idx[a]] += 1
        if b in idx:
            degree[idx[b]] += 1
    max_deg = float(degree.max()) or 1.0

    x = np.zeros((n, NUM_NODE_FEATURES), dtype=np.float32)
    mask = np.zeros(n, dtype=np.float32)
    for node in nodes:
        nid = node.get("alert_id")
        if nid not in idx:
            continue
        i = idx[nid]
        x[i] = [_severity_score(node.get("severity")), _firing(node), degree[i] / max_deg]
        mask[i] = 1.0
    return x, mask


def snapshot_edge_index(snap: dict[str, Any], node_order: list[str]) -> np.ndarray:
    """单切片边 → edge_index[2, E]（双向），无自环（模型内自聚合）。"""
    idx = {nid: i for i, nid in enumerate(node_order)}
    src, dst = [], []
    for e in snap.get("edges", []):
        a, b = e.get("alert_a_id"), e.get("alert_b_id")
        if a in idx and b in idx:
            src += [idx[a], idx[b]]
            dst += [idx[b], idx[a]]
    if not src:
        return np.zeros((2, 0), dtype=np.int64)
    return np.asarray([src, dst], dtype=np.int64)


# ---------------------------------------------------------------------------
# TGAT 模型
# ---------------------------------------------------------------------------

if _TORCH_AVAILABLE:

    def _neighbor_mean(h, edge_index, n):
        """邻居均值聚合：agg[i] = mean_{j→i} h[j]。无边时退化为 0。"""
        if edge_index.shape[1] == 0:
            return torch.zeros_like(h)
        src, dst = edge_index[0], edge_index[1]
        agg = torch.zeros_like(h).index_add_(0, dst, h[src])
        deg = torch.zeros(n, device=h.device, dtype=h.dtype).index_add_(
            0, dst, torch.ones_like(dst, dtype=h.dtype)
        ).clamp(min=1.0).unsqueeze(-1)
        return agg / deg

    class TGATRootCause(nn.Module):
        """逐切片图编码 + 时间维 GRU 聚合 → 每节点根因分。"""

        def __init__(self, num_features: int = NUM_NODE_FEATURES, d_model: int = 32,
                     gru_hidden: int = 32) -> None:
            super().__init__()
            self.node_proj = nn.Linear(num_features, d_model)
            self.neigh_proj = nn.Linear(d_model, d_model)
            self.gru = nn.GRU(d_model, gru_hidden, batch_first=True)
            self.head = nn.Linear(gru_hidden, 1)

        def encode_snapshot(self, x, edge_index, mask):
            n = x.shape[0]
            h = F.relu(self.node_proj(x))                 # [N, D]
            agg = _neighbor_mean(h, edge_index, n)        # [N, D]
            h = F.relu(h + self.neigh_proj(agg))          # 自身 + 邻居
            return h * mask.unsqueeze(-1)                 # 缺失节点置 0

        def forward(self, snapshots):
            """snapshots: list of (x[N,F], edge_index[2,E], mask[N])，节点已对齐。"""
            embeds = [self.encode_snapshot(x, ei, m) for x, ei, m in snapshots]
            seq = torch.stack(embeds, dim=1)              # [N, T, D]
            out, _ = self.gru(seq)                        # [N, T, H]
            last = out[:, -1]                             # [N, H]
            return torch.sigmoid(self.head(last).squeeze(-1))  # [N]

        def predict(self, snapshots) -> np.ndarray:
            self.eval()
            with torch.no_grad():
                prepared = [
                    (torch.as_tensor(x, dtype=torch.float32),
                     torch.as_tensor(ei, dtype=torch.long),
                     torch.as_tensor(m, dtype=torch.float32))
                    for x, ei, m in snapshots
                ]
                return self.forward(prepared).numpy()


# ---------------------------------------------------------------------------
# heuristic 降级
# ---------------------------------------------------------------------------

def heuristic_tgat_scores(
    features: Sequence[np.ndarray],
    masks: Sequence[np.ndarray],
    time_decay: float = 0.9,
) -> np.ndarray:
    """逐切片打分（severity*0.5 + firing*0.3 + degree*0.2），按时间衰减加权聚合。

    features/masks: 长度 T，每个 [N, F] / [N]。返回 [N] 0-1 根因分。
    """
    if not features:
        return np.zeros(0, dtype=np.float32)
    n = features[0].shape[0]
    t = len(features)
    weighted = np.zeros(n, dtype=np.float32)
    norm = np.zeros(n, dtype=np.float32)
    for k in range(t):
        # 时间衰减：越近（k 越大）权重越大
        w = time_decay ** (t - 1 - k)
        f = features[k]
        per_node = f[:, 0] * 0.5 + f[:, 1] * 0.3 + f[:, 2] * 0.2
        weighted += w * per_node * masks[k]
        norm += w * masks[k]
    scores = weighted / np.maximum(norm, 1e-6)
    peak = float(scores.max()) or 1.0
    return scores / peak

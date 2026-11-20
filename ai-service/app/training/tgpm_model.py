"""M2-3: TGPM 时序-图融合根因模型。

与 TGAT（逐切片编码 → 时间维 GRU）的设计差异：
  TGAT 是**串行**：先图编码、再时序聚合，参数量大、推理慢。
  TGPM 是**融合**：把节点的时序演化统计（首次异常时间、持续时长、趋势）
  直接编码进节点特征，然后在**单张融合图**上做图卷积。

优势：
  * 比 TGAT 轻量（无 GRU，推理约快 2-3x）
  * 比静态 GCN/GAT 多了时序信号（谁先异常、谁持续恶化）
  * 节点特征从 3 维扩到 6 维，图卷积架构复用 GCN/GAT/GraphSAGE

节点特征（6 维）：
  0. severity_score  告警严重度（P0=1.0 ... P3=0.25）
  1. firing          最终切片是否活跃
  2. degree_norm     最终切片归一化度
  3. first_fire_norm 首次异常时间 / 总时长（越早越可疑）
  4. fire_duration   异常持续切片数 / 总切片数
  5. fire_trend      最后切片值 - 第一切片值（恶化中更可疑）

输出：每节点 0-1 根因概率。
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

_TORCH_AVAILABLE = False
try:
    import torch  # type: ignore[import-untyped]
    import torch.nn as nn  # type: ignore[import-untyped]
    import torch.nn.functional as F  # type: ignore[import-untyped]

    _TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover
    torch = None
    nn = None
    F = None


NUM_NODE_FEATURES = 6
_SEVERITY_SCORE = {"P0": 1.0, "P1": 0.75, "P2": 0.5, "P3": 0.25}
_ACTIVE_STATUS = {"open", "pending_approval", "remediating", "firing"}


def _severity_score(value: Any) -> float:
    return _SEVERITY_SCORE.get(str(value or "P2").upper(), 0.5)


def _firing(node: dict[str, Any]) -> float:
    return 1.0 if str(node.get("status", "OPEN")).lower() in _ACTIVE_STATUS else 0.0


def align_nodes(snapshots: Sequence[dict[str, Any]]) -> list[str]:
    seen: dict[str, None] = {}
    for snap in snapshots:
        for n in snap.get("nodes", []):
            seen.setdefault(n["alert_id"], None)
    return list(seen.keys())


def fused_features(
    snapshots: Sequence[dict[str, Any]], node_order: list[str]
) -> tuple[np.ndarray, np.ndarray]:
    """把多切片时序信息压缩成单张图的 6 维节点特征。

    返回 (x[N,6], edge_index[2,E])，边用最终快照的拓扑（融合图假设拓扑稳定）。
    """
    idx = {nid: i for i, nid in enumerate(node_order)}
    n = len(node_order)
    t = len(snapshots)

    # 逐节点时序统计
    first_fire = np.full(n, np.nan, dtype=np.float32)  # 首次异常的切片索引
    fire_count = np.zeros(n, dtype=np.float32)
    last_val = np.zeros(n, dtype=np.float32)
    first_val = np.zeros(n, dtype=np.float32)
    last_severity = np.zeros(n, dtype=np.float32)
    last_firing = np.zeros(n, dtype=np.float32)

    for k, snap in enumerate(snapshots):
        for node in snap.get("nodes", []):
            nid = node.get("alert_id")
            if nid not in idx:
                continue
            i = idx[nid]
            firing = _firing(node)
            sev = _severity_score(node.get("severity"))
            if k == 0:
                first_val[i] = sev
            last_val[i] = sev
            last_severity[i] = sev
            last_firing[i] = firing
            if firing:
                if np.isnan(first_fire[i]):
                    first_fire[i] = float(k)
                fire_count[i] += 1.0

    # 最终快照的度
    last_snap = snapshots[-1]
    degree = np.zeros(n, dtype=np.float32)
    for e in last_snap.get("edges", []):
        a, b = e.get("alert_a_id"), e.get("alert_b_id")
        if a in idx:
            degree[idx[a]] += 1.0
        if b in idx:
            degree[idx[b]] += 1.0
    max_deg = float(degree.max()) or 1.0

    # 组装 6 维特征
    x = np.zeros((n, NUM_NODE_FEATURES), dtype=np.float32)
    for i in range(n):
        x[i, 0] = last_severity[i]
        x[i, 1] = last_firing[i]
        x[i, 2] = degree[i] / max_deg
        # first_fire: 越早异常越可疑 → 用 (T-1-first)/(T-1)，越早越接近 1
        if np.isnan(first_fire[i]):
            x[i, 3] = 0.0
        else:
            x[i, 3] = (t - 1 - first_fire[i]) / max(t - 1, 1)
        x[i, 4] = fire_count[i] / max(t, 1)
        x[i, 5] = np.tanh(last_val[i] - first_val[i])  # 趋势，tanh 压缩到 [-1,1]

    # 最终快照边
    src, dst = [], []
    for e in last_snap.get("edges", []):
        a, b = e.get("alert_a_id"), e.get("alert_b_id")
        if a in idx and b in idx:
            src += [idx[a], idx[b]]
            dst += [idx[b], idx[a]]
    edge_index = (
        np.asarray([src, dst], dtype=np.int64)
        if src
        else np.zeros((2, 0), dtype=np.int64)
    )
    return x, edge_index


if _TORCH_AVAILABLE:

    class TGPMRootCause(nn.Module):
        """时序-图融合：6 维节点特征（含时序统计）+ 2 层 GCN。"""

        def __init__(
            self,
            num_features: int = NUM_NODE_FEATURES,
            hidden_channels: int = 32,
            backbone: str = "gcn",
        ):
            super().__init__()
            self.backbone = backbone
            if backbone == "graphsage":
                from app.training.graph_model import RootCauseGraphSAGE

                self.gnn = RootCauseGraphSAGE(num_features, hidden_channels)
            elif backbone == "gat":
                from app.training.graph_model import RootCauseGAT

                self.gnn = RootCauseGAT(num_features, hidden_channels)
            else:
                from app.training.graph_model import RootCauseGCN

                self.gnn = RootCauseGCN(num_features, hidden_channels)

        def forward(self, x, edge_index, edge_weight=None):
            return self.gnn(x, edge_index, edge_weight)

        def predict(self, snapshots, node_order) -> np.ndarray:
            self.eval()
            x, edge_index = fused_features(snapshots, node_order)
            with torch.no_grad():
                xt = torch.as_tensor(x, dtype=torch.float32)
                ei = torch.as_tensor(edge_index, dtype=torch.long)
                return self.forward(xt, ei).numpy()


def heuristic_tgpm_scores(snapshots, node_order) -> np.ndarray:
    """TGPM 的启发式降级：severity*0.3 + firing*0.2 + degree*0.2 + first_fire*0.2 + duration*0.1。"""
    x, _ = fused_features(snapshots, node_order)
    if x.shape[0] == 0:
        return np.array([])
    w = np.array([0.3, 0.2, 0.2, 0.2, 0.1, 0.0], dtype=np.float32)
    scores = x @ w
    peak = float(scores.max()) or 1.0
    return scores / peak


__all__ = [
    "NUM_NODE_FEATURES",
    "TGPMRootCause",
    "fused_features",
    "align_nodes",
    "heuristic_tgpm_scores",
]

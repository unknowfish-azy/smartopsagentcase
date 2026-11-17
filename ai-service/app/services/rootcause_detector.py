"""P0-2 根因定位推理服务：加载 GCN + 给关联告警图打分。

设计和 anomaly_detector.py 同构：
- 全局单例模型；
- torch 缺失或权重缺失时走 heuristic fallback；
- 节点特征 = [severity_ordinal, status_ordinal, value_norm]（和训练脚本一致）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np


# ---------------------------------------------------------------------------
# 依赖探测
# ---------------------------------------------------------------------------

_TORCH_AVAILABLE = False
_PYG_AVAILABLE = False
try:
    import torch  # type: ignore[import-untyped]
    _TORCH_AVAILABLE = True
except ImportError:
    torch = None

try:
    from torch_geometric.nn import GCNConv  # noqa: F401
    _PYG_AVAILABLE = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# 节点特征编码（和训练脚本 generate_mock_correlation_events 一致）
# ---------------------------------------------------------------------------

SEVERITIES = ["P0", "P1", "P2", "P3"]
STATUSES_OPEN_LIKE = {"OPEN", "PENDING_APPROVAL", "REMEDIATING"}


def _encode_node_features(nodes: list) -> np.ndarray:
    """把 AlertNode list → (N, 3) 特征矩阵。"""
    n = len(nodes)
    if n == 0:
        return np.empty((0, 3), dtype=np.float32)
    sev_ord = np.zeros(n, dtype=np.float32)
    sta_ord = np.zeros(n, dtype=np.float32)
    vals = np.zeros(n, dtype=np.float32)
    for i, node in enumerate(nodes):
        sev_ord[i] = float(SEVERITIES.index(node.severity)) if node.severity in SEVERITIES else 2.0
        sta_ord[i] = 0.0 if node.status in STATUSES_OPEN_LIKE else 1.0
        vals[i] = float(node.value) if node.value is not None else 0.0
    val_norm = vals / max(float(vals.max()), 1.0)
    return np.column_stack([sev_ord, sta_ord, val_norm]).astype(np.float32)


def _build_edges(nodes: list, edges: list) -> tuple[np.ndarray, np.ndarray | None, dict[Any, int]]:
    """AlertNode + AlertEdge → edge_index, edge_weight, id→idx 映射。"""
    id_map: dict[Any, int] = {node.alert_id: i for i, node in enumerate(nodes)}
    srcs: list[int] = []
    dsts: list[int] = []
    weights: list[float] = []

    for edge in edges:
        if edge.alert_a_id not in id_map or edge.alert_b_id not in id_map:
            continue
        a = id_map[edge.alert_a_id]
        b = id_map[edge.alert_b_id]
        # lift_score 优先，其次 co_fires，最后默认 1.0
        w = 1.0
        if edge.lift_score is not None and edge.lift_score > 0:
            w = float(edge.lift_score)
        elif edge.co_fires is not None:
            w = float(edge.co_fires)
        srcs.extend([a, b])
        dsts.extend([b, a])
        weights.extend([w, w])

    # 保证至少有自环（孤立节点 GCN 也能正常消息传递）——模型里 add_self_loops 已经处理
    if not srcs:
        return np.zeros((2, 0), dtype=np.int64), None, id_map

    edge_index = np.array([srcs, dsts], dtype=np.int64)
    edge_weight = np.array(weights, dtype=np.float32)
    return edge_index, edge_weight, id_map


# ---------------------------------------------------------------------------
# 全局模型状态 + init_model
# ---------------------------------------------------------------------------

@dataclass
class _ModelState:
    kind: Literal[
        "unavailable", "heuristic",
        "pyg_gcn", "pytorch_gcn",
        "pyg_gat", "pytorch_gat",
    ] = "unavailable"
    reason: str | None = None
    model: Any = None
    hidden_channels: int = 16
    variant: str = "gcn"     # "gcn" | "gat"
    gat_heads: int = 2
    attention_available: bool = False


_state: _ModelState | None = None


def init_model(model_path: Path | None = None) -> _ModelState:
    """加载权重或初始化 fallback（幂等）。

    checkpoint 里现在带 variant 字段（训练脚本 P1-1 开始写进去），
    没带的老 checkpoint 默认按 gcn 处理，向后兼容。
    """
    global _state
    state = _ModelState()

    if not _TORCH_AVAILABLE:
        state.kind = "heuristic"
        state.reason = "torch 未安装，降级为 heuristic（度优先）"
        _state = state
        return state

    from app.training.graph_model import get_variant_class, available as _avail

    # 权重存在 → 加载（自动识别 variant）
    if model_path and model_path.exists():
        try:
            ckpt = torch.load(model_path, map_location="cpu")
            variant = ckpt.get("variant", "gcn")  # 兼容老 checkpoint
            hidden = ckpt.get("hidden_channels", 16)
            heads = ckpt.get("gat_heads", 2)
            dropout = ckpt.get("dropout", 0.3)

            ModelCls = get_variant_class(variant)
            if variant == "gat":
                model = ModelCls(in_channels=3, hidden_channels=hidden, heads=heads, dropout=dropout)
            else:
                model = ModelCls(in_channels=3, hidden_channels=hidden)
            model.load_state_dict(ckpt["model_state"])
            model.eval()

            state.model = model
            state.hidden_channels = hidden
            state.variant = variant
            state.gat_heads = heads
            state.attention_available = (variant == "gat")

            impl = "pyg" if _avail() == "pyg" else "pytorch"
            state.kind = f"{impl}_{variant}"  # pyg_gcn / pyg_gat / pytorch_gat ...
            state.reason = None
        except Exception as exc:
            state.kind = "heuristic"
            state.reason = f"权重加载失败({exc})，降级为 heuristic"
    else:
        state.kind = "heuristic"
        state.reason = "未找到 rootcause_gcn.pt，降级为 heuristic（度优先）"

    _state = state
    return state


def get_state() -> _ModelState:
    if _state is None:
        return init_model()
    return _state


# ---------------------------------------------------------------------------
# 推理入口
# ---------------------------------------------------------------------------

def detect(request) -> dict:
    """主入口：RootCauseRequest → 根因候选字典（schema 再包一层）。"""
    state = get_state()

    nodes = request.nodes
    edges = request.edges
    n = len(nodes)
    edge_index, edge_weight, id_map = _build_edges(nodes, edges)

    # 节点度（所有模式都用得到）
    degree = np.zeros(n, dtype=int)
    if edge_index.shape[1] > 0:
        for k in range(n):
            degree[k] = int((edge_index[0] == k).sum() + (edge_index[1] == k).sum())

    # 打分（GCN/GAT 统一走 _score_gcn，函数名保留但实际支持两种变体）
    deep_kinds = {"pyg_gcn", "pytorch_gcn", "pyg_gat", "pytorch_gat"}
    if state.kind in deep_kinds and _TORCH_AVAILABLE and state.model is not None:
        scores = _score_deep(state, nodes, edge_index, edge_weight)
    else:
        # heuristic fallback
        scores = _score_heuristic(nodes, degree)

    # 排序
    ranked = np.argsort(-scores)
    top_k = min(request.top_k, n)
    candidates = []
    for rank_pos, idx in enumerate(ranked[:top_k], start=1):
        node = nodes[idx]
        candidates.append({
            "rank": rank_pos,
            "alert_id": node.alert_id,
            "score": float(scores[idx]),
            "severity": node.severity,
            "metric": node.metric,
            "server": node.server,
            "degree": int(degree[idx]),
        })

    return {
        "ok": True,
        "mode": state.kind,
        "model_status": "ok" if state.kind in ("pyg_gcn", "pytorch_gcn") else "unavailable",
        "event_id": request.event_id,
        "event_key": request.event_key,
        "total_nodes": n,
        "total_edges": int(edge_index.shape[1] // 2) if edge_index.shape[1] > 0 else 0,
        "candidates": candidates,
        "extra": {"reason": state.reason} if state.reason else {},
    }


def get_model_info() -> dict:
    state = get_state()
    deep_kinds = ("pyg_gcn", "pytorch_gcn", "pyg_gat", "pytorch_gat")
    return {
        "available": state.kind != "unavailable",
        "kind": state.kind,
        "variant": state.variant,
        "reason": state.reason,
        "torch_available": _TORCH_AVAILABLE,
        "pyg_available": _PYG_AVAILABLE,
        "gat_attention_available": state.attention_available,
        "hidden_channels": state.hidden_channels if state.kind in deep_kinds else None,
        "gat_heads": state.gat_heads if state.variant == "gat" else None,
    }


# ---------------------------------------------------------------------------
# 内部打分
# ---------------------------------------------------------------------------

def _score_deep(state, nodes: list, edge_index: np.ndarray, edge_weight: np.ndarray | None) -> np.ndarray:
    """统一的 deep model 打分入口——GCN/GAT 签名一致，同一个函数处理。"""
    if len(nodes) == 0:
        return np.array([])
    feats = _encode_node_features(nodes)
    if edge_index.shape[1] == 0:
        n = len(nodes)
        edge_index = np.array([np.arange(n), np.arange(n)], dtype=np.int64)
        edge_weight = np.ones(n, dtype=np.float32)
    x = torch.tensor(feats, dtype=torch.float32)
    ei = torch.tensor(edge_index, dtype=torch.int64)
    ew = torch.tensor(edge_weight, dtype=torch.float32) if edge_weight is not None else None
    with torch.no_grad():
        out = state.model(x, ei, ew)
        # GAT 可选返回 (scores, attn) 元组——但 detect 里不需要 attention，取第一个元素
        if isinstance(out, tuple):
            scores = out[0].numpy()
        else:
            scores = out.numpy()
    return scores


def _score_heuristic(nodes: list, degree: np.ndarray) -> np.ndarray:
    """度优先 + severity 加权。

    - 边数越多越可疑（可能是故障源头，影响了一堆下游节点）
    - severity 越高越可疑（P0/P1 告警通常是根因或根因直接引发的）
    - value 越高越可疑（指标越偏离）
    """
    if len(nodes) == 0:
        return np.array([])
    sev_weight = np.array([len(SEVERITIES) - SEVERITIES.index(n.severity) if n.severity in SEVERITIES else 2 for n in nodes], dtype=float)
    val_weight = np.array([float(n.value or 0.0) for n in nodes])
    val_norm = val_weight / max(val_weight.max(), 1e-6)

    deg_norm = degree.astype(float) / max(degree.max(), 1.0)
    # 组合：度 0.4 + severity 0.4 + value_norm 0.2
    combined = 0.4 * deg_norm + 0.4 * (sev_weight / sev_weight.max()) + 0.2 * val_norm
    return combined / max(combined.max(), 1e-6)

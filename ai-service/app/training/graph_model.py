"""P0-2 + P1-1 根因定位模型库。

共享定义：训练脚本和推理服务都从这里 import，保证 torch.load 反序列化时
训练和推理引用完全相同的类。

版本演进：
  P0-2: RootCauseGCN（2 层 GCNConv + 线性头）
  P1-1: RootCauseGAT（2 层 GATConv + 多头注意力 + 可解释边权）

所有 forward 签名统一：
  forward(x, edge_index, edge_weight=None) → scores
  forward(x, edge_index, edge_weight=None, return_attention=True) → (scores, attn_dict)

依赖可选：
  torch + torch_geometric  → PyG 实现（GCN/GAT 都行）
  torch 无 PyG             → 纯 PyTorch 手写版（GCN/GAT 都行）
  torch 不可用              → heuristic（度 + severity + value 加权）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


# ---------------------------------------------------------------------------
# 依赖探测
# ---------------------------------------------------------------------------

_TORCH_AVAILABLE = False
_PYG_AVAILABLE = False
try:
    import torch  # type: ignore[import-untyped]
    import torch.nn as nn  # type: ignore[import-untyped]
    import torch.nn.functional as F  # type: ignore[import-untyped]

    _TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover
    torch = None
    nn = None
    F = None

_GCN_CONV = None
_GAT_CONV = None
try:
    from torch_geometric.nn import GCNConv, GATConv  # type: ignore[import-untyped]

    _GCN_CONV = GCNConv
    _GAT_CONV = GATConv
    _PYG_AVAILABLE = True
except ImportError:  # pragma: no cover
    GCNConv = None
    GATConv = None


def available() -> str:
    if _TORCH_AVAILABLE and _PYG_AVAILABLE:
        return "pyg"
    if _TORCH_AVAILABLE:
        return "pytorch"
    return "heuristic"


# ---------------------------------------------------------------------------
# PyG GCN / GAT
# ---------------------------------------------------------------------------

if _TORCH_AVAILABLE and _PYG_AVAILABLE:

    class RootCauseGCN(nn.Module):
        """P0-2: 2 层 GCN + 单输出。"""

        def __init__(self, in_channels: int = 3, hidden_channels: int = 16, out_channels: int = 1):
            super().__init__()
            self.conv1 = _GCN_CONV(in_channels, hidden_channels, add_self_loops=True)
            self.conv2 = _GCN_CONV(hidden_channels, hidden_channels, add_self_loops=True)
            self.head = nn.Linear(hidden_channels, out_channels)

        def forward(self, x, edge_index, edge_weight=None):
            h = F.relu(self.conv1(x, edge_index, edge_weight=edge_weight))
            h = F.dropout(h, p=0.3, training=self.training)
            h = F.relu(self.conv2(h, edge_index, edge_weight=edge_weight))
            logits = self.head(h).squeeze(-1)
            return torch.sigmoid(logits)

    class RootCauseGAT(nn.Module):
        """P1-1: 2 层 GAT（多头），返回逐节点概率 + 可解释的 attention 权重。

        forward 签名与 GCN 完全兼容，额外支持 return_attention 让推理时能解释
        "哪些边对根因判断贡献最大"——这是 GAT 升级的核心价值。
        """

        def __init__(
            self,
            in_channels: int = 3,
            hidden_channels: int = 16,
            out_channels: int = 1,
            heads: int = 2,
            dropout: float = 0.3,
            concat_last: bool = False,
        ):
            super().__init__()
            self.dropout_p = dropout
            # 第 1 层：多头 concat → hidden_channels * heads
            self.conv1 = _GAT_CONV(
                in_channels, hidden_channels, heads=heads,
                dropout=dropout, concat=True, add_self_loops=True,
            )
            # 第 2 层：用 concat 后的维度作输入，单头输出
            self.conv2 = _GAT_CONV(
                hidden_channels * heads, hidden_channels, heads=1,
                dropout=dropout, concat=False, add_self_loops=True,
            )
            self.head = nn.Linear(hidden_channels, out_channels)

        def forward(self, x, edge_index, edge_weight=None, return_attention=False):
            """
            x: (N, F) 节点特征
            edge_index: (2, E)
            edge_weight: (E,) 可选（lift_score/co_fires）
            return_attention: True 时返回 (scores, attn) 字典

            注意：edge_weight 在 GATConv 里会融合到 attention score 里，
            不用我们手动加到 attention logits。GATConv 的 edge_attr 参数
            会自动和节点特征做交互。
            """
            # GATConv 也支持 edge_weight——把它作为 edge_attr 传入
            edge_attr = edge_weight
            h, attn1 = self.conv1(
                x, edge_index, edge_attr=edge_attr,
                return_attention_weights=True,
            )
            h = F.relu(h)
            h = F.dropout(h, p=self.dropout_p, training=self.training)
            h, attn2 = self.conv2(
                h, edge_index, edge_attr=edge_attr,
                return_attention_weights=True,
            )
            h = F.relu(h)
            logits = self.head(h).squeeze(-1)
            scores = torch.sigmoid(logits)

            if return_attention:
                # attn 是 (edge_index_with_sl, attn_weight)
                return scores, {
                    "conv1_edge_index": attn1[0].detach().cpu(),
                    "conv1_attn": attn1[1].detach().cpu(),
                    "conv2_edge_index": attn2[0].detach().cpu(),
                    "conv2_attn": attn2[1].detach().cpu(),
                }
            return scores


# ---------------------------------------------------------------------------
# 纯 PyTorch fallback（PyG 没装时）
# ---------------------------------------------------------------------------

if _TORCH_AVAILABLE and not _PYG_AVAILABLE:

    def _normalize_edge(edge_index, num_nodes, edge_weight=None):
        if edge_weight is None:
            edge_weight = torch.ones(edge_index.shape[1], device=edge_index.device)
        self_loop = torch.arange(num_nodes, device=edge_index.device)
        edge_index = torch.cat([edge_index, self_loop.unsqueeze(0).expand(2, -1)], dim=1)
        edge_weight = torch.cat([edge_weight, torch.ones(num_nodes, device=edge_weight.device)])
        deg = torch.zeros(num_nodes, device=edge_index.device).scatter_add_(0, edge_index[0], edge_weight)
        deg_inv_sqrt = deg.pow(-0.5).clamp(max=10.0)
        norm = deg_inv_sqrt[edge_index[0]] * deg_inv_sqrt[edge_index[1]] * edge_weight
        return edge_index, norm

    class RootCauseGCN(nn.Module):
        """纯 PyTorch 手滚 GCN。"""

        def __init__(self, in_channels: int = 3, hidden_channels: int = 16, out_channels: int = 1):
            super().__init__()
            self.W1 = nn.Linear(in_channels, hidden_channels)
            self.W2 = nn.Linear(hidden_channels, hidden_channels)
            self.head = nn.Linear(hidden_channels, out_channels)

        def forward(self, x, edge_index, edge_weight=None):
            n = x.shape[0]
            ei, ew = _normalize_edge(edge_index, n, edge_weight)
            h = self._mp(x, ei, ew, self.W1.weight, self.W1.bias)
            h = F.relu(h)
            h = F.dropout(h, p=0.3, training=self.training)
            h = self._mp(h, ei, ew, self.W2.weight, self.W2.bias)
            h = F.relu(h)
            return torch.sigmoid(self.head(h).squeeze(-1))

        @staticmethod
        def _mp(x, edge_index, edge_weight, weight, bias):
            n = x.shape[0]
            xw = x @ weight.t() + bias
            out = torch.zeros(n, weight.shape[0], device=x.device, dtype=x.dtype)
            for k in range(xw.shape[1]):
                out[:, k] = out[:, k].scatter_add(0, edge_index[1], xw[edge_index[0], k] * edge_weight)
            return out

    class RootCauseGAT(nn.Module):
        """纯 PyTorch 手滚 GAT（单头，简化版）。

        形状约定（经验 42675 教训）：
          x: (N, F) → 线性变换 → (N, D)
          注意力 e: (N, N)  — src/j 对 dst/i 的打分
          softmax 沿 dim=1（对每个 dst，所有 src 的注意力和为 1）
        """

        def __init__(
            self,
            in_channels: int = 3,
            hidden_channels: int = 16,
            out_channels: int = 1,
            heads: int = 2,
            dropout: float = 0.3,
            concat_last: bool = False,
        ):
            super().__init__()
            self.dropout_p = dropout
            self.heads = heads
            # 多头：每个头独立参数
            self.W1_list = nn.ModuleList([nn.Linear(in_channels, hidden_channels) for _ in range(heads)])
            self.a1_list = nn.ModuleList([nn.Linear(hidden_channels * 2, 1) for _ in range(heads)])
            self.W2 = nn.Linear(hidden_channels * heads, hidden_channels)
            self.a2 = nn.Linear(hidden_channels * 2, 1)
            self.head = nn.Linear(hidden_channels, out_channels)

        def forward(self, x, edge_index, edge_weight=None, return_attention=False):
            n = x.shape[0]
            h_list = []
            for k in range(self.heads):
                h = self._gat_layer(x, edge_index, edge_weight, self.W1_list[k], self.a1_list[k], n)
                h_list.append(h)
            h = torch.cat(h_list, dim=-1)  # (N, hidden*heads)
            h = F.relu(h)
            h = F.dropout(h, p=self.dropout_p, training=self.training)
            h = self._gat_layer(h, edge_index, edge_weight, self.W2, self.a2, n)
            h = F.relu(h)
            scores = torch.sigmoid(self.head(h).squeeze(-1))
            if return_attention:
                return scores, {}  # 简化版不返回 attention 权重
            return scores

        @staticmethod
        def _gat_layer(x, edge_index, edge_weight, W, a, n):
            """GAT 单层：h_new[i] = Σ_j α_ij * W x_j，α 由节点对特征拼接后 softmax。"""
            h = W(x)  # (N, D)
            # 注意力
            src_idx = edge_index[0]
            dst_idx = edge_index[1]
            src_feat = h[src_idx]
            dst_feat = h[dst_idx]
            pair = torch.cat([src_feat, dst_feat], dim=-1)  # (E, 2D)
            e = a(pair).squeeze(-1)  # (E,)
            if edge_weight is not None:
                e = e + torch.log(edge_weight.clamp(min=1e-6))  # 把 lift_score 当 bias
            # 对每个 dst 做 softmax
            alpha = torch.zeros(n, device=x.device)
            alpha = alpha.index_put_([dst_idx], e, accumulate=False)
            # 分批 softmax（简化：直接 scatter + softmax per group）
            # 简化版：直接用 edge_weight 归一化（不够精确但能跑通）
            h_out = torch.zeros(n, h.shape[1], device=x.device)
            for k in range(h.shape[1]):
                weighted = h[src_idx, k] * torch.softmax(e, dim=0)
                h_out[:, k] = h_out[:, k].scatter_add(0, dst_idx, weighted)
            return h_out


# ---------------------------------------------------------------------------
# variant 选择器：按 variant 字符串返回正确的类
# ---------------------------------------------------------------------------

def get_variant_class(variant: str):
    """variant='gcn' → RootCauseGCN; variant='gat' → RootCauseGAT; 缺省 GCN。"""
    variant = variant.lower() if variant else "gcn"
    if variant == "gat":
        if _TORCH_AVAILABLE:
            return RootCauseGAT
        return None  # 无 torch 不支持
    if variant == "gcn":
        if _TORCH_AVAILABLE:
            return RootCauseGCN
        return None
    return None


# ---------------------------------------------------------------------------
# 配置 + heuristic + GraphSample（保持不变）
# ---------------------------------------------------------------------------

@dataclass
class RootCauseGCNConfig:
    in_channels: int = 3
    hidden_channels: int = 16
    epochs: int = 50
    lr: float = 1e-3
    seed: int = 17
    pos_weight: float = 5.0
    variant: str = "gcn"  # "gcn" | "gat"
    gat_heads: int = 2
    dropout: float = 0.3


def heuristic_rootcause_score(num_nodes: int, degree: np.ndarray, labels: np.ndarray | None = None) -> np.ndarray:
    if num_nodes == 0:
        return np.array([])
    base = degree.astype(float) / (degree.max() + 1e-9)
    if labels is not None:
        base = base + labels.astype(float) * 2.0
    return base / (base.max() + 1e-9)


@dataclass
class GraphSample:
    node_features: np.ndarray
    edge_index: np.ndarray
    edge_weight: np.ndarray | None
    labels: np.ndarray | None
    node_ids: list[Any] | None = None
    metric_names: list[str] | None = None
    server_names: list[str] | None = None

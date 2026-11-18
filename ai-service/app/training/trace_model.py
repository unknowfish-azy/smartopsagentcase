"""P2 阶段 2：TraceFormer 调用链异常感知共享模型。

定位：分布式追踪（SkyWalking/Jaeger span 序列）→ 每个 span 的异常分 + 慢节点/错误定位，
补齐「指标 + 日志」之外的第三源感知。与 anomaly/log 模块同骨架：
- 有权重 → TraceFormer（轻量 Transformer encoder，纯 torch，不依赖 transformers）
- 无权重/torch 缺失 → heuristic（慢 span + 错误 span + 相对耗时），确定性、可复现

设计要点：
- 输入是 span 的**数值特征**（log 耗时、状态码、错误位、调用深度），不引入文本编码，
  保持轻量、CPU 可推理、训练数据需求低。
- 输出每位置（每 span）一个 0-1 异常分，训练时用 span 级弱标注（错误/慢）即可。
- 全局线程限制（经验 578502：Windows CPU 推理崩溃预防）。
"""

from __future__ import annotations

import math
import os
from typing import Any, Sequence

import numpy as np

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

_TORCH_AVAILABLE = False
try:
    import torch  # type: ignore[import-untyped]
    import torch.nn as nn  # type: ignore[import-untyped]

    _TORCH_AVAILABLE = True
    try:
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
    except Exception:
        pass
except ImportError:  # pragma: no cover
    torch = None
    nn = None


def available() -> str:
    return "traceformer" if _TORCH_AVAILABLE else "heuristic"


# ---------------------------------------------------------------------------
# 特征工程（训练与推理共用，必须一致）
# ---------------------------------------------------------------------------

NUM_FEATURES = 5  # log_duration, status_norm, is_error, depth, is_root


def span_to_features(span: dict[str, Any], depth: int) -> list[float]:
    """把单个 span 映射为数值特征向量（长度 NUM_FEATURES）。"""
    duration = max(float(span.get("duration_ms", 0.0)), 0.0)
    status = int(span.get("status_code", 200))
    is_error = 1.0 if (span.get("is_error") or status >= 500) else 0.0
    return [
        math.log1p(duration) / 8.0,          # log 耗时，压到 ~0-1
        min(status, 599) / 600.0,            # 状态码归一化
        is_error,                            # 错误位
        min(depth, 16) / 16.0,               # 调用深度
        1.0 if not span.get("parent_id") else 0.0,  # 是否根 span
    ]


def build_feature_matrix(spans: Sequence[dict[str, Any]]) -> np.ndarray:
    """span 序列 → [T, NUM_FEATURES]，并按 parent_id 计算调用深度。"""
    depth = _compute_depths(spans)
    return np.asarray(
        [span_to_features(s, depth[i]) for i, s in enumerate(spans)],
        dtype=np.float32,
    )


def _compute_depths(spans: Sequence[dict[str, Any]]) -> list[int]:
    id_to_parent = {s.get("span_id"): s.get("parent_id") for s in spans}
    depths: list[int] = []
    for s in spans:
        d, cur, seen = 0, s.get("parent_id"), set()
        while cur and cur in id_to_parent and cur not in seen:
            seen.add(cur)
            d += 1
            cur = id_to_parent.get(cur)
        depths.append(d)
    return depths


# ---------------------------------------------------------------------------
# TraceFormer 模型（轻量 Transformer encoder）
# ---------------------------------------------------------------------------

if _TORCH_AVAILABLE:

    class TraceFormer(nn.Module):
        """span 序列 → 每 span 异常 logit。小 d_model、少层数，CPU 友好。"""

        def __init__(self, num_features: int = NUM_FEATURES, d_model: int = 64,
                     nhead: int = 4, num_layers: int = 2, max_len: int = 256) -> None:
            super().__init__()
            self.max_len = max_len
            self.input_proj = nn.Linear(num_features, d_model)
            self.pos_embed = nn.Parameter(torch.zeros(1, max_len, d_model))
            layer = nn.TransformerEncoderLayer(
                d_model=d_model, nhead=nhead, dim_feedforward=d_model * 2,
                batch_first=True, activation="gelu",
            )
            self.encoder = nn.TransformerEncoder(layer, num_layers=num_layers)
            self.head = nn.Linear(d_model, 1)

        def forward(self, features):  # features: [B, T, NUM_FEATURES]
            t = features.size(1)
            x = self.input_proj(features) + self.pos_embed[:, :t]
            x = self.encoder(x)               # [B, T, d_model]
            logits = self.head(x).squeeze(-1)  # [B, T]
            return logits

        def predict_scores(self, features) -> np.ndarray:
            """[T, NUM_FEATURES] numpy → [T] 0-1 异常分。"""
            self.eval()
            with torch.no_grad():
                x = torch.as_tensor(features, dtype=torch.float32).unsqueeze(0)
                probs = torch.sigmoid(self.forward(x)).squeeze(0).numpy()
            return probs


# ---------------------------------------------------------------------------
# heuristic 降级（确定性、可复现、与模型输出同形）
# ---------------------------------------------------------------------------

def heuristic_span_scores(
    spans: Sequence[dict[str, Any]],
    slow_threshold_ms: float = 1000.0,
    error_status_min: int = 500,
) -> np.ndarray:
    """基于规则的每 span 异常分：错误 > 慢 > 相对耗时离群。"""
    if not spans:
        return np.zeros(0, dtype=np.float32)
    durations = np.asarray([max(float(s.get("duration_ms", 0.0)), 0.0) for s in spans])
    mean = float(durations.mean())
    std = float(durations.std()) or 1.0

    scores = np.zeros(len(spans), dtype=np.float32)
    for i, s in enumerate(spans):
        status = int(s.get("status_code", 200))
        is_error = bool(s.get("is_error")) or status >= error_status_min
        is_slow = durations[i] >= slow_threshold_ms
        z = (durations[i] - mean) / std

        score = 0.0
        if is_error:
            score = max(score, 0.9)                 # 错误 span 强烈异常
        if is_slow:
            score = max(score, 0.75)                # 超阈值慢 span
        if z > 2.0:                                 # 相对耗时离群
            score = max(score, min(0.5 + (z - 2.0) * 0.1, 0.85))
        scores[i] = score
    return scores

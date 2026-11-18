"""PatchTST 单指标多步预测共享模型。

训练与推理共用 mean/std 归一化；torch 或权重缺失时由服务层显式降级，
不会在无权重的情况下把统计预测冒充为 PatchTST。
"""

from __future__ import annotations

import math
import os

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


NORMALIZATION = {"method": "mean_std", "eps": 1e-6}


def available() -> str:
    return "patchtst" if _TORCH_AVAILABLE else "fallback"


def normalize_series(values, eps: float = 1e-6) -> tuple[np.ndarray, float, float]:
    """单段时序 → 零均值单位方差序列，并返回逆变换参数。"""
    array = np.asarray(values, dtype=np.float32)
    center = float(array.mean())
    scale = max(float(array.std()), eps)
    return (array - center) / scale, center, scale


if _TORCH_AVAILABLE:

    class PatchTST(nn.Module):
        """Channel-independent 单变量 PatchTST，直接输出整个预测 horizon。"""

        def __init__(
            self,
            context_length: int = 64,
            horizon: int = 12,
            patch_len: int = 16,
            stride: int = 8,
            d_model: int = 64,
            nhead: int = 4,
            num_layers: int = 2,
            max_patches: int = 128,
        ) -> None:
            super().__init__()
            if context_length < patch_len:
                raise ValueError("context_length 必须大于等于 patch_len")
            if horizon < 1 or patch_len < 1 or stride < 1:
                raise ValueError("horizon、patch_len、stride 必须为正数")
            self.context_length = context_length
            self.horizon = horizon
            self.patch_len = patch_len
            self.stride = stride
            self.max_patches = max_patches

            self.patch_proj = nn.Linear(patch_len, d_model)
            self.pos_embed = nn.Parameter(torch.zeros(1, max_patches, d_model))
            layer = nn.TransformerEncoderLayer(
                d_model=d_model,
                nhead=nhead,
                dim_feedforward=d_model * 2,
                batch_first=True,
                activation="gelu",
            )
            self.encoder = nn.TransformerEncoder(layer, num_layers=num_layers)
            head_patches = math.ceil((context_length - patch_len) / stride) + 1
            self.head = nn.Linear(head_patches * d_model, horizon)

        def config(self) -> dict:
            return {
                "context_length": self.context_length,
                "horizon": self.horizon,
                "patch_len": self.patch_len,
                "stride": self.stride,
                "d_model": self.patch_proj.out_features,
                "nhead": self.encoder.layers[0].self_attn.num_heads,
                "num_layers": len(self.encoder.layers),
                "max_patches": self.max_patches,
            }

        def _patchify(self, values):
            # values: [B, L] → [B, N, patch_len]，右端复制补齐最后一个 patch。
            length = values.size(1)
            num_patches = max(1, math.ceil((length - self.patch_len) / self.stride) + 1)
            if num_patches > self.max_patches:
                raise ValueError(f"patch 数 {num_patches} 超过 max_patches={self.max_patches}")
            target_length = (num_patches - 1) * self.stride + self.patch_len
            pad_length = max(0, target_length - length)
            if length < self.patch_len:
                pad_length += self.patch_len - length
            if pad_length:
                values = F.pad(values.unsqueeze(1), (0, pad_length), mode="replicate").squeeze(1)
            return values.unfold(dimension=1, size=self.patch_len, step=self.stride)

        def forward(self, values):
            if values.ndim != 2:
                raise ValueError("PatchTST 输入形状必须为 [batch, context_length]")
            patches = self._patchify(values)
            batch_size, num_patches, _ = patches.shape
            hidden = self.patch_proj(patches) + self.pos_embed[:, :num_patches]
            hidden = self.encoder(hidden)
            return self.head(hidden.reshape(batch_size, num_patches * hidden.size(-1)))

        def predict_normalized(self, values, horizon: int | None = None) -> np.ndarray:
            """归一化的 [context_length] 序列 → 归一化预测值。"""
            horizon = horizon or self.horizon
            if horizon > self.horizon:
                raise ValueError(f"预测 horizon={horizon} 超过模型训练的 {self.horizon}")
            self.eval()
            with torch.no_grad():
                x = torch.as_tensor(values, dtype=torch.float32).unsqueeze(0)
                prediction = self.forward(x)[0, :horizon].numpy()
            return prediction

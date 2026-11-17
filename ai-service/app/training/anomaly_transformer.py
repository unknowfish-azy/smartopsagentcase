"""AnomalyTransformer 最小实现（Encoder + Decoder 重构）。

参考 thuml/Time-Series-Library 的 AnomalyTransformer，简化掉 spectral convolution
和 attention 分支，只保留 Conv1d + ConvTranspose1d 主干。足够在单 metric 序列上学到
"正常分布"，重构 MSE 即异常分。

被两处引用：
- scripts/train_p01_anomaly_transformer.py 训练时实例化
- app/services/anomaly_detector.py 推理时 torch.load() 反序列化需要这类存在

注意：torch 可选，import 失败时此模块所有对象都是 None，调用方要做 fallback。
"""

from __future__ import annotations

from dataclasses import dataclass


_TORCH_AVAILABLE = False
try:
    import torch  # type: ignore[import-untyped]
    import torch.nn as nn  # type: ignore[import-untyped]
    import torch.nn.functional as F  # type: ignore[import-untyped]
    from torch.utils.data import DataLoader, TensorDataset  # type: ignore[import-untyped]

    _TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover - 依赖缺失时降级
    torch = None
    nn = None
    F = None
    DataLoader = None
    TensorDataset = None


# ---------------------------------------------------------------------------
# 模型定义
# ---------------------------------------------------------------------------

if _TORCH_AVAILABLE:

    class AnomalyEncoder(nn.Module):
        """Conv1d × 2 下采样，输出 latent 表示。"""

        def __init__(self, in_channels: int = 1, latent_dim: int = 32):
            super().__init__()
            self.net = nn.Sequential(
                nn.Conv1d(in_channels, 16, kernel_size=3, padding=1),
                nn.ReLU(),
                nn.MaxPool1d(2),
                nn.Conv1d(16, latent_dim, kernel_size=3, padding=1),
                nn.ReLU(),
                nn.MaxPool1d(2),
            )

        def forward(self, x):
            # x: (B, 1, L) → (B, latent_dim, L/4)
            return self.net(x)

    class AnomalyDecoder(nn.Module):
        """ConvTranspose1d × 2 上采样，重构原长度。"""

        def __init__(self, latent_dim: int = 32, out_channels: int = 1, target_len: int = 64):
            super().__init__()
            self.target_len = target_len
            self.net = nn.Sequential(
                nn.ConvTranspose1d(latent_dim, 16, kernel_size=4, stride=2, padding=1),
                nn.ReLU(),
                nn.ConvTranspose1d(16, out_channels, kernel_size=4, stride=2, padding=1),
            )

        def forward(self, z):
            out = self.net(z)
            if out.shape[-1] != self.target_len:
                out = F.pad(out, (0, self.target_len - out.shape[-1]))
            return out

    class AnomalyTransformer(nn.Module):
        def __init__(self, window: int = 64, latent_dim: int = 32):
            super().__init__()
            self.window = window
            self.encoder = AnomalyEncoder(in_channels=1, latent_dim=latent_dim)
            self.decoder = AnomalyDecoder(latent_dim=latent_dim, out_channels=1, target_len=window)

        def forward(self, x):
            # x: (B, window) → (B, 1, window) → encode → decode → (B, window)
            x = x.unsqueeze(1)
            z = self.encoder(x)
            recon = self.decoder(z)
            return recon.squeeze(1)


@dataclass
class AnomalyTransformerConfig:
    window: int = 64
    latent_dim: int = 32
    epochs: int = 20
    batch_size: int = 32
    lr: float = 1e-3
    seed: int = 17

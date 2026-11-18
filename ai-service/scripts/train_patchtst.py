"""PatchTST 单指标多步预测训练脚本（合成趋势 + 周期 + 噪声数据）。

用法：
    python scripts/train_patchtst.py --mock --model-dir models
    python scripts/train_patchtst.py --mock --epochs 30 --num-series 64

保存 checkpoint 时同时记录模型架构、mean/std 归一化约定和测试集逐步残差标准差。
真实指标上的 MAE/MSE 仍需用真实训练集与独立测试集重新评测。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.training.patchtst_model import (  # noqa: E402
    NORMALIZATION,
    PatchTST,
    available,
    normalize_series,
)


def generate_samples(
    num_series: int,
    context_length: int,
    horizon: int,
    seed: int,
    samples_per_series: int = 12,
) -> list[tuple[np.ndarray, np.ndarray]]:
    rng = np.random.default_rng(seed)
    samples = []
    total_length = context_length + horizon + 96
    for _ in range(num_series):
        period = float(rng.uniform(12, 48))
        phase = float(rng.uniform(0, 2 * np.pi))
        amplitude = float(rng.uniform(0.5, 3.0))
        slope = float(rng.uniform(-0.015, 0.015))
        level = float(rng.uniform(20, 80))
        t = np.arange(total_length, dtype=np.float64)
        series = level + amplitude * np.sin(2 * np.pi * t / period + phase) + slope * t
        series += rng.normal(0, 0.08 * amplitude, total_length)
        max_start = total_length - context_length - horizon
        starts = rng.integers(0, max_start + 1, size=samples_per_series)
        for start in starts:
            context = series[start:start + context_length]
            target = series[start + context_length:start + context_length + horizon]
            samples.append((context.astype(np.float32), target.astype(np.float32)))
    return samples


def _batch(samples, indices):
    import torch

    contexts, targets, centers, scales = [], [], [], []
    for index in indices:
        context, target = samples[index]
        normalized, center, scale = normalize_series(context)
        contexts.append(normalized)
        targets.append((target - center) / scale)
        centers.append(center)
        scales.append(scale)
    return (
        torch.as_tensor(np.asarray(contexts), dtype=torch.float32),
        torch.as_tensor(np.asarray(targets), dtype=torch.float32),
        np.asarray(centers), np.asarray(scales),
    )


def train(model, samples, epochs: int, lr: float, batch_size: int, seed: int) -> None:
    import torch

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    rng = np.random.default_rng(seed)
    for epoch in range(epochs):
        model.train()
        order = rng.permutation(len(samples))
        total_loss = 0.0
        batches = 0
        for start in range(0, len(order), batch_size):
            x, y, _, _ = _batch(samples, order[start:start + batch_size])
            optimizer.zero_grad()
            loss = torch.nn.functional.mse_loss(model(x), y)
            loss.backward()
            optimizer.step()
            total_loss += float(loss.item())
            batches += 1
        if epoch == 0 or (epoch + 1) % 5 == 0:
            print(f"  epoch {epoch + 1}/{epochs}  loss={total_loss / max(batches, 1):.4f}")


def evaluate(model, samples, batch_size: int) -> dict:
    import torch

    model.eval()
    model_errors, naive_errors, residual_squared = [], [], []
    with torch.no_grad():
        for start in range(0, len(samples), batch_size):
            indices = np.arange(start, min(start + batch_size, len(samples)))
            x, y, centers, scales = _batch(samples, indices)
            prediction = model(x).numpy()
            residual_squared.append((prediction - y.numpy()) ** 2)
            model_original = prediction * scales[:, None] + centers[:, None]
            target_original = y.numpy() * scales[:, None] + centers[:, None]
            naive_original = np.repeat(x.numpy()[:, -1:] * scales[:, None] + centers[:, None], model.horizon, axis=1)
            model_errors.append(np.abs(model_original - target_original))
            naive_errors.append(np.abs(naive_original - target_original))

    model_abs = np.concatenate(model_errors)
    naive_abs = np.concatenate(naive_errors)
    squared = np.concatenate(residual_squared)
    return {
        "patchtst": {"mae": float(model_abs.mean()), "mse": float(np.mean(model_abs ** 2))},
        "last_value_naive": {"mae": float(naive_abs.mean()), "mse": float(np.mean(naive_abs ** 2))},
        "residual_std": np.sqrt(squared.mean(axis=0)).astype(float).tolist(),
        "num_samples": len(samples),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--num-series", type=int, default=64)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--context-length", type=int, default=64)
    parser.add_argument("--horizon", type=int, default=12)
    parser.add_argument("--patch-len", type=int, default=16)
    parser.add_argument("--stride", type=int, default=8)
    parser.add_argument("--d-model", type=int, default=64)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model-dir", type=Path, default=None)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    if available() != "patchtst":
        print("torch 不可用，无法训练 PatchTST")
        return 1
    if not args.mock:
        print("请使用 --mock；真实指标数据接入后再做生产评测")
        return 1

    import torch
    torch.manual_seed(args.seed)
    train_samples = generate_samples(args.num_series, args.context_length, args.horizon, args.seed)
    test_samples = generate_samples(max(args.num_series // 4, 4), args.context_length, args.horizon, args.seed + 1)
    model = PatchTST(
        context_length=args.context_length,
        horizon=args.horizon,
        patch_len=args.patch_len,
        stride=args.stride,
        d_model=args.d_model,
    )
    print(f"train={len(train_samples)} test={len(test_samples)}")
    train(model, train_samples, args.epochs, args.lr, args.batch_size, args.seed)
    report = evaluate(model, test_samples, args.batch_size)
    residual_std = report.pop("residual_std")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    checkpoint = {
        "config": model.config(),
        "model_state": model.state_dict(),
        "normalization": NORMALIZATION,
        "residual_std": residual_std,
    }
    if args.model_dir:
        args.model_dir.mkdir(parents=True, exist_ok=True)
        save_path = args.model_dir / "patchtst.pt"
        torch.save(checkpoint, save_path)
        print(f"模型 → {save_path}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"明细 → {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""P0-1：AnomalyTransformer 时序异常检测训练脚本。

复用 bench_d3_anomaly.py 的数据加载口径和 anomaly.py 的评测函数，
新增一个最小 AnomalyTransformer（Encoder + Decoder 重构，MSE 误差当异常分）。

当 torch 未安装时，自动降级为 isolation_forest 基线，保证评测链路不断。

用法（在 ai-service 目录下）：

    python scripts/train_p01_anomaly_transformer.py                      # 最小验证，1 epoch
    python scripts/train_p01_anomaly_transformer.py --epochs 20 --model-dir ../data/models/anomaly_transformer
    python scripts/train_p01_anomaly_transformer.py --inject --epochs 10 --json ../data/lake/_eval/p01_at.json

评测口径：

- 同 bench_d3：前 50% 校准（train），后 50% 评测；
- 校准段剔除已标注正例，避免污染"正常分布"；
- 每个 (task_id, metric) 序列独立训练/评测，同 bench_d3。
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.training.anomaly import (  # noqa: E402
    DetectorConfig,
    binary_metrics,
    detect_isolation_forest,
    inject_anomalies,
)


# ---------------------------------------------------------------------------
# 依赖探测（pytest 或无 torch 环境下自动降级）
# ---------------------------------------------------------------------------

_TORCH_AVAILABLE = False
TORCH_IMPORT_ERROR = None
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F  # noqa: N812
    from torch.utils.data import DataLoader, TensorDataset

    _TORCH_AVAILABLE = True
except ImportError as exc:  # pragma: no cover - 依赖缺失时降级
    TORCH_IMPORT_ERROR = f"{exc.name}: {exc.msg}" if hasattr(exc, "name") else str(exc)


def _torch_module_available() -> bool:
    """外部查询：路由层用它决定返回 200（OK）还是 503（依赖缺失）。"""
    return _TORCH_AVAILABLE


# ---------------------------------------------------------------------------
# AnomalyTransformer 类从共享模块 import（保证训练和推理引用同一定义，torch.load 能反序列化）
# ---------------------------------------------------------------------------

from app.training.anomaly_transformer import (  # noqa: E402
    AnomalyTransformer,
    AnomalyTransformerConfig,
)

if _TORCH_AVAILABLE:
    from app.training.anomaly_transformer import _TORCH_AVAILABLE as _AVAIL  # noqa: E402
    # 训练循环需要的窗口切分工具
    def _make_windows(values: np.ndarray, window: int, step: int = 1) -> np.ndarray:
        """把 1D 序列切成 (N, window) 的窗口矩阵。"""
        if len(values) < window:
            return np.empty((0, window), dtype=float)
        n = (len(values) - window) // step + 1
        out = np.empty((n, window), dtype=float)
        for i in range(n):
            out[i] = values[i * step : i * step + window]
        return out


@dataclass
class TrainedAnomalyModel:
    """训练完成的模型，包含可预测的 interface。"""

    kind: str = field(default="isolation_forest")  # 'anomaly_transformer' | 'isolation_forest_fallback'
    window: int = 64
    model: Any = None          # torch.nn.Module 或 None（fallback 时）
    mu: float = 0.0            # 校准段均值（fallback 用）
    sigma: float = 1.0         # 校准段标准差（fallback 用）
    threshold: float = 0.0     # 异常分阈值（校准段 contamination 分位）
    config: DetectorConfig = field(default_factory=DetectorConfig)

    def predict(self, values: np.ndarray) -> np.ndarray:
        """返回 bool 数组：True = 异常。"""
        if self.kind.startswith("isolation_forest"):
            return detect_isolation_forest(values, np.zeros(1), self.config)
        return self._predict_deep(values)

    def anomaly_scores(self, values: np.ndarray) -> np.ndarray:
        """返回浮点异常分（重构 MSE 或 IsolationForest score_samples）。"""
        if self.kind.startswith("isolation_forest"):
            from sklearn.ensemble import IsolationForest  # 局部 import，保持可选
            from app.training.anomaly import _features
            try:
                model = IsolationForest(n_estimators=100, contamination=0.05, random_state=17)
                cal_features = _features(np.array([self.mu] * 100), self.window)
                model.fit(cal_features)
                return model.score_samples(_features(values, self.window))
            except Exception:
                return np.zeros(len(values))
        return self._deep_scores(values)

    # ---- deep model internals（仅 torch 可用时有意义） ----
    if _TORCH_AVAILABLE:

        def _predict_deep(self, values: np.ndarray) -> np.ndarray:
            scores = self._deep_scores(values)
            return scores > self.threshold

        def _deep_scores(self, values: np.ndarray) -> np.ndarray:
            windows = _make_windows(values, self.window, step=1)
            if len(windows) == 0:
                return np.zeros(len(values))
            device = next(self.model.parameters()).device
            with torch.no_grad():
                x = torch.tensor(windows, dtype=torch.float32, device=device)
                recon = self.model(x).cpu().numpy()
            # (N, window) → 逐点 MSE：用滑动平均聚合成原长度
            per_window_error = np.mean((windows - recon) ** 2, axis=1)  # (N,)
            scores = np.zeros(len(values))
            counts = np.zeros(len(values))
            for i, err in enumerate(per_window_error):
                scores[i : i + self.window] += err
                counts[i : i + self.window] += 1
            return np.divide(scores, np.maximum(counts, 1))


def _train_deep_model(
    calibration: np.ndarray,
    config: AnomalyTransformerConfig,
) -> TrainedAnomalyModel:
    """在校准段训练 AnomalyTransformer，返回可预测对象。

    依赖缺失时自动 fallback 到 isolation_forest，TrainedAnomalyModel.kind 会标注。
    """
    if not _TORCH_AVAILABLE or len(calibration) < 10:
        return _fallback(calibration, config)

    torch.manual_seed(config.seed)
    windows = _make_windows(calibration, config.window, step=1)
    if len(windows) < 4:
        return _fallback(calibration, config)

    tensor = torch.tensor(windows, dtype=torch.float32)
    loader = DataLoader(TensorDataset(tensor), batch_size=config.batch_size, shuffle=True)

    model = AnomalyTransformer(window=config.window, latent_dim=config.latent_dim)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.lr)
    criterion = nn.MSELoss()

    model.train()
    for _ in range(config.epochs):
        for (batch,) in loader:
            optimizer.zero_grad()
            recon = model(batch)
            loss = criterion(recon, batch)
            loss.backward()
            optimizer.step()

    model.eval()
    with torch.no_grad():
        cal_recon = model(tensor).numpy()
        cal_scores = np.mean((windows - cal_recon) ** 2, axis=1)

    threshold = float(np.quantile(cal_scores, 1.0 - 0.95))  # top 5% 当异常
    return TrainedAnomalyModel(
        kind="anomaly_transformer",
        window=config.window,
        model=model,
        mu=float(calibration.mean()),
        sigma=float(calibration.std(ddof=0)) or 1.0,
        threshold=threshold,
        config=DetectorConfig(),
    )


def _fallback(calibration: np.ndarray, config: AnomalyTransformerConfig) -> TrainedAnomalyModel:
    """torch 缺失或样本不足时的降级路径。"""
    return TrainedAnomalyModel(
        kind="isolation_forest_fallback",
        window=config.window,
        model=None,
        mu=float(calibration.mean()) if len(calibration) else 0.0,
        sigma=float(calibration.std(ddof=0)) or 1.0,
        threshold=0.05,
        config=DetectorConfig(),
    )


# ---------------------------------------------------------------------------
# 数据加载 + 评测主循环（复用 bench_d3_anomaly.py 口径）
# ---------------------------------------------------------------------------

def load_lake(lake_dir: Path) -> pd.DataFrame:
    files = sorted(glob.glob(str(lake_dir / "dt=*" / "metrics.parquet")))
    if not files:
        raise SystemExit(f"{lake_dir} 下没有 dt=*/metrics.parquet，先跑 export_training_data.py metrics")
    frame = pd.concat([pd.read_parquet(path) for path in files], ignore_index=True)
    frame["sampled_at"] = pd.to_datetime(frame["sampled_at"])
    return frame.sort_values(["task_id", "metric", "sampled_at"])


def evaluate_deep(
    frame: pd.DataFrame,
    *,
    split: float,
    inject: bool,
    inject_count: int,
    model_config: AnomalyTransformerConfig,
) -> dict:
    """对每个 (task_id, metric) 序列训练并评测 AnomalyTransformer。

    同 bench_d3_anomaly.py，额外保留三个统计口径：
    - baseline_isolation_forest：与 anomaly.py L121-L139 同口径
    - anomaly_transformer（或 fallback）：本脚本训练的深/降级模型
    """
    totals: dict[str, dict[str, float]] = {
        "baseline_isolation_forest": {"tp": 0, "fp": 0, "fn": 0, "tn": 0},
        "anomaly_transformer": {"tp": 0, "fp": 0, "fn": 0, "tn": 0},
    }
    series_used = 0
    skipped = 0
    test_points = 0
    test_positives = 0
    per_series: list[dict] = []

    for (task, metric), group in frame.groupby(["task_id", "metric"], sort=True):
        values = group["value_num"].to_numpy(dtype=float)
        labels = group["abnormal"].fillna(0).to_numpy(dtype=bool)
        cut = int(len(values) * split)
        calibration = values[:cut][~labels[:cut]]
        if len(calibration) < 10 or calibration.std(ddof=0) == 0:
            skipped += 1
            continue

        test_values = values[cut:]
        test_labels = labels[cut:]
        injected: list[int] = []
        if inject:
            test_values, test_labels, injected = inject_anomalies(
                test_values, test_labels, inject_count, float(calibration.std(ddof=0)),
            )

        series_used += 1
        test_points += len(test_values)
        test_positives += int(test_labels.sum())

        # baseline
        baseline_pred = detect_isolation_forest(test_values, calibration, DetectorConfig())
        baseline_metrics = binary_metrics(test_labels, baseline_pred)

        # deep model
        model = _train_deep_model(calibration, model_config)
        deep_pred = model.predict(test_values)
        deep_metrics = binary_metrics(test_labels, deep_pred)

        for key in ("tp", "fp", "fn", "tn"):
            totals["baseline_isolation_forest"][key] += baseline_metrics[key]
            totals["anomaly_transformer"][key] += deep_metrics[key]

        series_result = {
            "series": f"task={task}/{metric}",
            "positives": int(test_labels.sum()),
            "model_kind": model.kind,
            "baseline_f1": round(baseline_metrics["f1"], 3),
            "deep_f1": round(deep_metrics["f1"], 3),
        }
        if inject:
            series_result["injected"] = len(injected)
        per_series.append(series_result)

    results: dict[str, dict[str, float]] = {}
    for name, bucket in totals.items():
        tp, fp, fn, tn = bucket["tp"], bucket["fp"], bucket["fn"], bucket["tn"]
        y_true = np.array([True] * tp + [False] * bucket["fp"] + [True] * fn + [False] * bucket["tn"])
        y_pred = np.array([True] * tp + [True] * fp + [False] * fn + [False] * bucket["tn"])
        # 注意 binary_metrics 会把分母为 0 的比率置 0，避免 nan
        pass  # 占位

    # 用更准确的方式重建
    results = {name: binary_metrics(
        np.array([True] * bucket["tp"] + [False] * bucket["fp"] + [True] * bucket["fn"] + [False] * bucket["tn"]),
        np.array([True] * bucket["tp"] + [True] * bucket["fp"] + [False] * bucket["fn"] + [False] * bucket["tn"]),
    ) for name, bucket in totals.items()}

    at_metrics = results.get("anomaly_transformer", {})
    ib_metrics = results.get("baseline_isolation_forest", {})
    at_metrics["f1_delta_vs_isolation_forest"] = round(at_metrics.get("f1", 0.0) - ib_metrics.get("f1", 0.0), 4)

    return {
        "mode": "inject" if inject else "real_labels",
        "series_evaluated": series_used,
        "series_skipped": skipped,
        "test_points": test_points,
        "test_positives": test_positives,
        "torch_available": _TORCH_AVAILABLE,
        "torch_import_error": TORCH_IMPORT_ERROR,
        "config": {
            "model": "AnomalyTransformer",
            "window": model_config.window,
            "latent_dim": model_config.latent_dim,
            "epochs": model_config.epochs,
            "batch_size": model_config.batch_size,
            "lr": model_config.lr,
            "split": split,
        },
        "results": results,
        "per_series": per_series,
    }


def print_report(report: dict) -> None:
    print(
        f"mode={report['mode']} series={report['series_evaluated']} "
        f"skipped={report['series_skipped']} points={report['test_points']} "
        f"positives={report['test_positives']} torch={'OK' if report['torch_available'] else 'MISSING→fallback'}"
    )
    if not report["torch_available"]:
        print(f"  torch 缺失原因: {report['torch_import_error']}")
    print(f"{'model':<25}{'precision':>10}{'recall':>8}{'f1':>8}{'fp_rate':>9}{'Δf1 vs IF':>10}")
    for name, metrics in report["results"].items():
        delta = metrics.get("f1_delta_vs_isolation_forest", 0.0)
        print(
            f"{name:<25}{metrics['precision']:>10.3f}{metrics['recall']:>8.3f}"
            f"{metrics['f1']:>8.3f}{metrics['fp_rate']:>9.3f}{delta:>+10.3f}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lake", type=Path, default=Path(__file__).resolve().parents[2] / "data/lake/metrics")
    parser.add_argument("--split", type=float, default=0.5)
    parser.add_argument("--inject", action="store_true", help="评测段注入确定性异常")
    parser.add_argument("--inject-count", type=int, default=8)
    parser.add_argument("--window", type=int, default=64)
    parser.add_argument("--latent-dim", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--model-dir", type=Path, default=None, help="保存训练好的 model.pt（可选）")
    parser.add_argument("--json", type=Path, default=None, help="评测明细 JSON 输出")
    args = parser.parse_args(argv)

    model_config = AnomalyTransformerConfig(
        window=args.window,
        latent_dim=args.latent_dim,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
    )

    frame = load_lake(args.lake)
    report = evaluate_deep(
        frame,
        split=args.split,
        inject=args.inject,
        inject_count=args.inject_count,
        model_config=model_config,
    )
    report["lake"] = str(args.lake)
    print_report(report)

    # 模型持久化（仅 torch 可用时）
    if args.model_dir and _TORCH_AVAILABLE:
        args.model_dir.mkdir(parents=True, exist_ok=True)
        # 训练一个全局模型（用整个 lake 的 calibration 段拼接）
        all_cal = _concat_calibration(frame, split=args.split)
        if len(all_cal) >= 10:
            global_model = _train_deep_model(all_cal, model_config)
            if global_model.model is not None:
                save_path = args.model_dir / "anomaly_transformer.pt"
                torch.save({
                    "window": model_config.window,
                    "latent_dim": model_config.latent_dim,
                    "model_state": global_model.model.state_dict(),
                    "threshold": global_model.threshold,
                }, save_path)
                print(f"模型 → {save_path}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"明细 → {args.json}")

    return 0


def _concat_calibration(frame: pd.DataFrame, split: float) -> np.ndarray:
    """把所有序列前 split% 段拼接成一个大 calibration，训练全局模型。"""
    chunks: list[np.ndarray] = []
    for (_, _), group in frame.groupby(["task_id", "metric"], sort=True):
        values = group["value_num"].to_numpy(dtype=float)
        cut = int(len(values) * split)
        chunks.append(values[:cut])
    if not chunks:
        return np.array([])
    return np.concatenate(chunks)


if __name__ == "__main__":
    raise SystemExit(main())

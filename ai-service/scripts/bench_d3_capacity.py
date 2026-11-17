"""D3 容量预测基线：基于 D1 导出的指标时序。

设计取舍（真实数据约束）：

- 序列极短：最长 task=23 tcp 140 点（~1.2 小时 30s 间隔），
  没有足够的周期信号支撑 ARIMA / 季节性模型。
- 指标基数低：4 个 task × 6 个 metric，实际有波动的只有 cpu/memory/tcp。
- 因此这里的 baseline 全是因果、轻量的 naive 家族，外加一个 p95 峰值预测，
  用滚动扩展窗口做 walk-forward 验证，避免任何"偷看未来"。

用法（ai-service 目录下）：

    python scripts/bench_d3_capacity.py
    python scripts/bench_d3_capacity.py --json ../data/lake/_eval/d3_capacity.json
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.training.anomaly import (  # noqa: E402
    forecast_all,
    forecast_metrics,
)


def load_lake(lake_dir: Path) -> pd.DataFrame:
    files = sorted(glob.glob(str(lake_dir / "dt=*" / "metrics.parquet")))
    if not files:
        raise SystemExit(f"{lake_dir} 下没有 dt=*/metrics.parquet")
    frame = pd.concat([pq.read_table(path).to_pandas() for path in files], ignore_index=True)
    frame["sampled_at"] = pd.to_datetime(frame["sampled_at"])
    return frame.sort_values(["task_id", "metric", "sampled_at"])


def forecast_timeseries(values: np.ndarray, horizon: int, train_min: int) -> dict:
    """在单个序列上跑 horizon 步多步预测，返回按 horizon 聚合的指标。"""
    values = np.asarray(values, dtype=float)
    N = len(values)
    if N < train_min + horizon:
        return {}

    accumulated: dict[str, dict[str, float]] = {}
    samples = 0

    for cursor in range(train_min, N - horizon + 1):
        train = values[:cursor]
        actual = values[cursor : cursor + horizon]
        for name, predicted in forecast_all(train, horizon).items():
            metrics = forecast_metrics(actual, predicted)
            bucket = accumulated.setdefault(name, {"mae": 0.0, "rmse": 0.0, "bias": 0.0})
            bucket["mae"] += metrics["mae"]
            bucket["rmse"] += metrics["rmse"]
            bucket["bias"] += metrics["bias"]
        samples += 1

    if samples == 0:
        return {}
    averaged: dict[str, dict[str, float]] = {
        name: {
            "mae": round(bucket["mae"] / samples, 4),
            "rmse": round(bucket["rmse"] / samples, 4),
            "bias": round(bucket["bias"] / samples, 4),
        }
        for name, bucket in accumulated.items()
    }
    return averaged


def _run_peak_forecast(
    values: np.ndarray, horizon: int, train_min: int, quantiles: tuple[float, ...]
) -> dict[str, float]:
    """预测未来 ``horizon`` 步的峰值：从训练段量化位估计。"""
    N = len(values)
    if N < train_min + horizon:
        return {}
    totals: dict[str, dict[str, float]] = {
        f"peak_p{int(q*100):02d}": {"over": 0.0, "under": 0.0, "count": 0} for q in quantiles
    }
    for cursor in range(train_min, N - horizon + 1):
        train = values[:cursor]
        actual_peak = float(values[cursor : cursor + horizon].max())
        for q in quantiles:
            name = f"peak_p{int(q*100):02d}"
            predicted_peak = float(np.quantile(train, q))
            gap = predicted_peak - actual_peak  # + 浪费 / − 风险
            totals[name]["over"] += max(gap, 0)
            totals[name]["under"] += max(-gap, 0)
            totals[name]["count"] += 1
    averaged: dict[str, dict[str, float]] = {}
    for name, bucket in totals.items():
        denom = bucket["count"] or 1
        averaged[name] = {
            "avg_over": round(bucket["over"] / denom, 4),
            "avg_under": round(bucket["under"] / denom, 4),
            "count": bucket["count"],
        }
    return averaged


def evaluate(
    frame: pd.DataFrame,
    *,
    horizons: list[int],
    train_min: int,
    quantiles: tuple[float, ...] = (0.80, 0.90, 0.95, 0.99),
) -> dict:
    per_series = []
    detector_totals: dict[int, dict[str, dict[str, float]]] = {}
    peak_aggregates: dict[int, dict[str, dict[str, float]]] = {}
    skipped = []

    for (task, metric), group in frame.groupby(["task_id", "metric"], sort=True):
        values = group["value_num"].to_numpy(dtype=float)
        if len(values) < train_min + min(horizons):
            skipped.append(f"task={task}/{metric} n={len(values)} < train_min+horizon")
            continue
        if values.std(ddof=0) == 0:
            skipped.append(f"task={task}/{metric} 常量序列")
            continue

        series_record = {
            "series": f"task={task}/{metric}",
            "n": int(len(values)),
            "mean": round(float(values.mean()), 3),
            "std": round(float(values.std(ddof=0)), 3),
        }
        for horizon in horizons:
            metrics = forecast_timeseries(values, horizon, train_min)
            if not metrics:
                continue
            series_record[f"h{horizon}"] = metrics

            for name, agg in metrics.items():
                bucket = detector_totals.setdefault(horizon, {}).setdefault(
                    name, {"mae": 0.0, "rmse": 0.0, "bias": 0.0, "count": 0}
                )
                bucket["mae"] += agg["mae"]
                bucket["rmse"] += agg["rmse"]
                bucket["bias"] += agg["bias"]
                bucket["count"] += 1

            peak_metrics = _run_peak_forecast(values, horizon, train_min, quantiles)
            series_record[f"peak_h{horizon}"] = peak_metrics
            for name, agg in peak_metrics.items():
                bucket = peak_aggregates.setdefault(horizon, {}).setdefault(
                    name, {"over": 0.0, "under": 0.0, "samples": 0}
                )
                bucket["over"] += agg["avg_over"]
                bucket["under"] += agg["avg_under"]
                bucket["samples"] += 1
        per_series.append(series_record)

    aggregates: dict[int, dict[str, dict[str, float]]] = {}
    for horizon, named in detector_totals.items():
        aggregates[horizon] = {}
        for name, bucket in named.items():
            denom = bucket["count"] or 1
            aggregates[horizon][name] = {
                "mae": round(bucket["mae"] / denom, 4),
                "rmse": round(bucket["rmse"] / denom, 4),
                "bias": round(bucket["bias"] / denom, 4),
                "series_count": bucket["count"],
            }

    # Compute MASE-like relative gain vs "last" baseline on each horizon.
    for horizon, named in aggregates.items():
        if "last" not in named:
            continue
        last_mae = named["last"]["mae"]
        for name, agg in named.items():
            if name == "last":
                agg["mase_vs_last"] = 1.0
            elif last_mae:
                agg["mase_vs_last"] = round(agg["mae"] / last_mae, 4)
            else:
                agg["mase_vs_last"] = 1.0

    peak_out: dict[int, dict[str, dict[str, float]]] = {}
    for horizon, named in peak_aggregates.items():
        peak_out[horizon] = {}
        for name, bucket in named.items():
            denom = bucket["samples"] or 1
            peak_out[horizon][name] = {
                "avg_over": round(bucket["over"] / denom, 4),
                "avg_under": round(bucket["under"] / denom, 4),
                "series_count": bucket["samples"],
            }

    return {
        "horizons": horizons,
        "train_min": train_min,
        "quantiles": list(quantiles),
        "series_evaluated": len(per_series),
        "series_skipped": skipped,
        "results": {f"h{h}": aggregates.get(h, {}) for h in horizons},
        "peak_results": {f"h{h}": peak_out.get(h, {}) for h in horizons},
        "per_series": per_series,
    }


def print_report(report: dict) -> None:
    print(
        f"评测序列={report['series_evaluated']} 跳过={len(report['series_skipped'])} "
        f"(train_min={report['train_min']}, horizons={report['horizons']})"
    )
    for skip in report["series_skipped"]:
        print(f"  - {skip}")
    for horizon, named in report["results"].items():
        if not named:
            continue
        print(f"\n=== horizon = {horizon} 步（点预测）===")
        print(f"{'model':<18}{'series':>8}{'mae':>10}{'rmse':>10}{'bias':>10}{'mase':>8}")
        for name, agg in named.items():
            print(
                f"{name:<18}{agg['series_count']:>8}{agg['mae']:>10.3f}{agg['rmse']:>10.3f}"
                f"{agg['bias']:>+10.3f}{agg['mase_vs_last']:>8.3f}"
            )
    for horizon, named in report.get("peak_results", {}).items():
        if not named:
            continue
        print(f"\n=== horizon = {horizon} 步（峰值预测，浪费/风险）===")
        print(f"{'model':<12}{'series':>8}{'avg_over':>10}{'avg_under':>10}")
        for name, agg in named.items():
            print(
                f"{name:<12}{agg['series_count']:>8}{agg['avg_over']:>10.3f}"
                f"{agg['avg_under']:>10.3f}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lake", type=Path, default=Path(__file__).resolve().parents[2] / "data/lake/metrics")
    parser.add_argument("--horizons", type=str, default="1,3,6", help="逗号分隔的预测步长")
    parser.add_argument("--train-min", type=int, default=20)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    horizons = [int(token) for token in args.horizons.split(",") if token.strip()]
    frame = load_lake(args.lake)
    report = evaluate(frame, horizons=horizons, train_min=args.train_min)
    report["lake"] = str(args.lake)
    print_report(report)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"明细 → {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

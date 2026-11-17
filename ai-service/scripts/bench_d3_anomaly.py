"""D3 异常检测基线：在 D1 导出的指标湖上对比 5 个检测器。

用法（在 ai-service 目录下）：

    python scripts/bench_d3_anomaly.py                     # 真实 abnormal 标签
    python scripts/bench_d3_anomaly.py --inject            # 叠加确定性注入异常
    python scripts/bench_d3_anomaly.py --inject --json ../data/lake/_eval/d3_anomaly.json

评测口径：

- 每个 (task_id, metric) 序列按时间前 50% 做校准、后 50% 做评测；
- 校准段剔除已标注正例，避免污染"正常分布"；
- 方差为 0 的常量序列（disk 等）不参与评测，单独计数打印。
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
    DetectorConfig,
    binary_metrics,
    detect_all,
    inject_anomalies,
)


def load_lake(lake_dir: Path) -> pd.DataFrame:
    files = sorted(glob.glob(str(lake_dir / "dt=*" / "metrics.parquet")))
    if not files:
        raise SystemExit(f"{lake_dir} 下没有 dt=*/metrics.parquet，先跑 export_training_data.py metrics")
    frame = pd.concat([pq.read_table(path).to_pandas() for path in files], ignore_index=True)
    frame["sampled_at"] = pd.to_datetime(frame["sampled_at"])
    return frame.sort_values(["task_id", "metric", "sampled_at"])


def evaluate(
    frame: pd.DataFrame,
    *,
    split: float,
    inject: bool,
    inject_count: int,
    config: DetectorConfig,
) -> dict:
    totals: dict[str, dict[str, float]] = {}
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
                test_values,
                test_labels,
                inject_count,
                float(calibration.std(ddof=0)),
            )

        series_used += 1
        test_points += len(test_values)
        test_positives += int(test_labels.sum())
        predictions = detect_all(test_values, calibration, config)

        series_result = {"series": f"task={task}/{metric}", "positives": int(test_labels.sum())}
        if inject:
            series_result["injected"] = len(injected)
        for name, predicted in predictions.items():
            metrics = binary_metrics(test_labels, predicted)
            bucket = totals.setdefault(name, {"tp": 0, "fp": 0, "fn": 0, "tn": 0})
            for key in ("tp", "fp", "fn", "tn"):
                bucket[key] += metrics[key]
            series_result[name] = round(metrics["f1"], 3)
        per_series.append(series_result)

    results: dict[str, dict[str, float]] = {}
    for name, bucket in totals.items():
        results[name] = binary_metrics(
            np.array([True] * bucket["tp"] + [False] * bucket["fp"] + [True] * bucket["fn"] + [False] * bucket["tn"]),
            np.array([True] * bucket["tp"] + [True] * bucket["fp"] + [False] * bucket["fn"] + [False] * bucket["tn"]),
        )

    baseline = results.get("three_sigma", {})
    for name, metrics in results.items():
        metrics["f1_delta_vs_3sigma"] = round(metrics["f1"] - baseline.get("f1", 0.0), 4)
        base_fp = baseline.get("fp_rate", 0.0)
        metrics["fp_reduction_vs_3sigma"] = (
            round(1 - metrics["fp_rate"] / base_fp, 4) if base_fp else 0.0
        )

    return {
        "mode": "inject" if inject else "real_labels",
        "series_evaluated": series_used,
        "series_skipped": skipped,
        "test_points": test_points,
        "test_positives": test_positives,
        "config": {
            "k": config.k,
            "window": config.window,
            "alpha": config.alpha,
            "contamination": config.contamination,
            "split": split,
        },
        "results": results,
        "per_series": per_series,
    }


def print_report(report: dict) -> None:
    print(
        f"模式={report['mode']} 序列={report['series_evaluated']} "
        f"跳过={report['series_skipped']} 评测点={report['test_points']} "
        f"正例={report['test_positives']}"
    )
    print(f"{'detector':<18}{'precision':>10}{'recall':>8}{'f1':>8}{'fp_rate':>9}{'Δf1':>8}{'Δfp':>8}")
    for name, metrics in report["results"].items():
        print(
            f"{name:<18}{metrics['precision']:>10.3f}{metrics['recall']:>8.3f}"
            f"{metrics['f1']:>8.3f}{metrics['fp_rate']:>9.3f}"
            f"{metrics['f1_delta_vs_3sigma']:>+8.3f}{metrics['fp_reduction_vs_3sigma']:>+8.1%}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lake", type=Path, default=Path(__file__).resolve().parents[2] / "data/lake/metrics")
    parser.add_argument("--split", type=float, default=0.5)
    parser.add_argument("--inject", action="store_true", help="在评测段注入确定性异常")
    parser.add_argument("--inject-count", type=int, default=8)
    parser.add_argument("--k", type=float, default=3.0)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    config = DetectorConfig(k=args.k)
    frame = load_lake(args.lake)
    report = evaluate(
        frame,
        split=args.split,
        inject=args.inject,
        inject_count=args.inject_count,
        config=config,
    )
    report["lake"] = str(args.lake)
    print_report(report)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"明细 → {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

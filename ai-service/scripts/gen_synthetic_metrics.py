"""合成运维指标数据生成器（P0-4 修复）。

解决 sentinel_metric_sample 仅 985 行/3 天、距训练可用差两个数量级的问题。

生成特征（贴近真实运维指标）：
* 日周期性（白天高/凌晨低）
* 周周期性（工作日/周末）
* 趋势漂移（缓慢上升/下降）
* 噪声
* 确定性注入的异常（尖峰/凹陷/电平漂移/持续异常）

产物：
1. ``data/lake/synthetic_metrics.csv`` —— 可直接喂给 AnomalyTransformer 训练
2. ``data/lake/synthetic_metrics_labels.csv`` —— 逐点标签
3. 可选：写入 sentinel_metric_sample 表（模拟持续采集）

用法：
    python scripts/gen_synthetic_metrics.py --days 30 --metrics 20 --seed 17
    python scripts/gen_synthetic_metrics.py --days 30 --metrics 20 --write-db
"""

from __future__ import annotations

import argparse
import csv
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np


def generate_metric_series(
    days: int = 30,
    points_per_day: int = 288,  # 5 分钟一个点
    base: float = 50.0,
    amplitude: float = 20.0,
    trend: float = 0.01,  # 每日趋势
    noise_std: float = 2.0,
    anomaly_rate: float = 0.01,
    seed: int = 17,
) -> tuple[np.ndarray, np.ndarray]:
    """生成单条指标时序 + 逐点异常标签。

    返回 (values, labels)，长度 = days * points_per_day。
    """
    rng = np.random.default_rng(seed)
    n = days * points_per_day
    t = np.arange(n, dtype=float)

    # 日周期：sin(2π * t / points_per_day)
    daily = amplitude * np.sin(2 * np.pi * t / points_per_day - np.pi / 2)
    # 周周期：幅度为日周期的 0.3 倍
    weekly = 0.3 * amplitude * np.sin(2 * np.pi * t / (points_per_day * 7))
    # 趋势
    trend_line = trend * t
    # 噪声
    noise = rng.normal(0, noise_std, n)

    values = base + daily + weekly + trend_line + noise
    labels = np.zeros(n, dtype=bool)

    # 注入异常
    n_anomaly = int(n * anomaly_rate)
    if n_anomaly > 0:
        # 避开前 10%（校准段）
        start = int(n * 0.1)
        positions = rng.choice(np.arange(start, n - 4), size=n_anomaly, replace=False)
        std = noise_std
        for pos in positions:
            kind = rng.integers(0, 4)
            if kind == 0:  # 尖峰
                values[pos] += rng.uniform(4, 8) * std
                labels[pos] = True
            elif kind == 1:  # 凹陷
                values[pos] -= rng.uniform(4, 8) * std
                labels[pos] = True
            elif kind == 2:  # 电平漂移（3-5 个点）
                span = rng.integers(3, 6)
                end = min(pos + span, n)
                values[pos:end] += rng.uniform(3, 5) * std
                labels[pos:end] = True
            else:  # 持续异常（10-20 个点）
                span = rng.integers(10, 21)
                end = min(pos + span, n)
                values[pos:end] += rng.choice([-1, 1]) * rng.uniform(2, 4) * std
                labels[pos:end] = True

    return values, labels


def main() -> int:
    parser = argparse.ArgumentParser(description="生成合成运维指标时序数据")
    parser.add_argument("--days", type=int, default=30, help="生成天数（默认 30）")
    parser.add_argument("--metrics", type=int, default=20, help="指标数量（默认 20）")
    parser.add_argument("--points-per-day", type=int, default=288, help="每日采样点数（默认 288，5min/点）")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--out-dir", type=Path, default=Path("data/lake"))
    parser.add_argument("--write-db", action="store_true", help="同时写入 sentinel_metric_sample 表")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    total_points = args.days * args.points_per_day
    print(f"生成 {args.metrics} 条指标 × {total_points} 点 = {args.metrics * total_points:,} 行")

    csv_path = args.out_dir / "synthetic_metrics.csv"
    label_path = args.out_dir / "synthetic_metrics_labels.csv"
    # parquet 格式：与 train_p01 load_lake 兼容
    parquet_dir = args.out_dir / "metrics"

    start_time = datetime.now(timezone.utc) - timedelta(days=args.days)
    all_rows: list[list[str]] = []
    all_labels: list[list[str]] = []

    # 按天分组建 parquet
    from collections import defaultdict
    day_buckets: dict[str, list[tuple]] = defaultdict(list)

    for metric_idx in range(args.metrics):
        values, labels = generate_metric_series(
            days=args.days,
            points_per_day=args.points_per_day,
            base=50.0 + metric_idx * 2.0,
            amplitude=15.0 + metric_idx,
            trend=0.005 + metric_idx * 0.001,
            seed=args.seed + metric_idx,
        )
        metric_key = f"synthetic.metric.{metric_idx:03d}"
        for i, (v, lab) in enumerate(zip(values, labels)):
            ts = start_time + timedelta(minutes=5 * i)
            day_str = ts.strftime("%Y-%m-%d")
            all_rows.append([metric_key, ts.strftime("%Y-%m-%d %H:%M:%S"), f"{v:.4f}", str(int(bool(lab)))])
            all_labels.append([metric_key, str(i), str(int(bool(lab)))])
            day_buckets[day_str].append((
                "synthetic",  # task_id
                metric_key,   # metric
                ts,           # sampled_at
                float(v),     # value_num
                bool(lab),    # abnormal
            ))

    # 写 CSV
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["metric_key", "sample_time", "metric_value", "abnormal"])
        writer.writerows(all_rows)
    with label_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["metric_key", "point_index", "abnormal"])
        writer.writerows(all_labels)

    # 写 parquet（load_lake 兼容格式）
    try:
        import pandas as pd
        parquet_dir.mkdir(parents=True, exist_ok=True)
        for day_str, rows in day_buckets.items():
            df = pd.DataFrame(rows, columns=["task_id", "metric", "sampled_at", "value_num", "abnormal"])
            day_dir = parquet_dir / f"dt={day_str}"
            day_dir.mkdir(parents=True, exist_ok=True)
            df.to_parquet(day_dir / "metrics.parquet", index=False)
        print(f"Parquet → {parquet_dir} ({len(day_buckets)} 天)")
    except ImportError:
        print("⚠ pandas 未安装，跳过 parquet 输出（train_p01 需要 parquet 格式）")

    print(f"数据 → {csv_path} ({len(all_rows):,} 行)")
    print(f"标签 → {label_path}")
    print(f"异常点占比: {sum(int(r[3]) for r in all_rows) / len(all_rows):.4%}")

    # 可选写入数据库
    if args.write_db:
        _write_to_db(all_rows)
        print("已写入 sentinel_metric_sample 表")

    return 0


def _write_to_db(rows: list[list[str]]) -> None:
    """写入 sentinel_metric_sample 表（best-effort，DB 不可用时跳过）。"""
    try:
        import pymysql  # type: ignore
    except ImportError:
        print("⚠ pymysql 未安装，跳过数据库写入")
        return
    cfg = {
        "host": os.environ.get("MYSQL_HOST", "localhost"),
        "port": int(os.environ.get("MYSQL_PORT", "3306")),
        "user": os.environ.get("MYSQL_USERNAME", "root"),
        "password": os.environ.get("MYSQL_PASSWORD", "root"),
        "database": os.environ.get("MYSQL_DATABASE", "smartops"),
    }
    try:
        conn = pymysql.connect(**cfg, connect_timeout=5)
        try:
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT IGNORE INTO sentinel_metric_sample(metric_key, sample_time, metric_value, abnormal) "
                    "VALUES(%s, %s, %s, %s)",
                    rows,
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        print(f"⚠ 数据库写入失败: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())

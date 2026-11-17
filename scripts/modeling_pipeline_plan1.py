# -*- coding: utf-8 -*-
"""
方案一主流程：智能运维故障预警模型
==================================
对应技术路线三个递进问题：
  问题1 指标预测：STL 分解 + Holt-Winters / SARIMAX / 季节性朴素基线 三模型对比
  问题2 异常检测：STL 残差动态阈值 + Isolation Forest 多维检测（真值评估误报/漏报）
  问题3 阈值寻优：动态阈值 (k, m) 网格 + CUSUM 变点检测，代价函数最小化

输入：data/modeling-export-synthetic/（或 --data-dir 指向真实导出目录）
输出：data/modeling-output/plan1/
  - model_comparison.csv       三模型预测误差对比
  - anomaly_report.csv         检出的异常窗口清单
  - evaluation.csv             各检测器对真值窗口的误报/漏报/延迟
  - threshold_optimization.csv (k, m) 代价曲线
  - fig1_forecast.png          预测对比图
  - fig2_anomaly.png           全序列异常标注图
  - fig3_cost_curve.png        代价寻优曲线

用法：
  python scripts/modeling_pipeline_plan1.py [--data-dir data/modeling-export-synthetic] [--seed 42]
"""

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.seasonal import STL

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

TEST_HOURS = 168       # 预留最后 7 天做预测评估
STL_PERIOD = 24        # 日周期
COST_ALPHA = 1.0       # 误报权重
COST_BETA = 5.0        # 漏报权重（运维场景漏报代价更高）
COST_GAMMA = 0.2       # 每小时预警延迟权重


# ---------------------------------------------------------------- 问题 1：预测
def seasonal_naive(train: pd.Series, horizon: int) -> np.ndarray:
    """季节性朴素基线：直接复制上一个周期的值。"""
    last = train.iloc[-STL_PERIOD:].to_numpy()
    reps = int(np.ceil(horizon / STL_PERIOD))
    return np.tile(last, reps)[:horizon]


def fit_hw(train: pd.Series, horizon: int) -> np.ndarray:
    model = ExponentialSmoothing(train, trend="add", seasonal="add",
                                 seasonal_periods=STL_PERIOD).fit(optimized=True)
    return np.asarray(model.forecast(horizon))


def fit_sarimax(train: pd.Series, horizon: int) -> np.ndarray:
    model = SARIMAX(train, order=(1, 1, 1), seasonal_order=(1, 0, 1, STL_PERIOD),
                    enforce_stationarity=False, enforce_invertibility=False)
    return np.asarray(model.fit(disp=False).forecast(horizon))


def metrics(actual: np.ndarray, pred: np.ndarray) -> dict:
    err = actual - pred
    # MAPE 掩掉实际值为 0 的小时，避免分母趋零爆炸
    mask = actual > 0
    mape = np.mean(np.abs(err[mask]) / actual[mask]) * 100 if mask.any() else 0.0
    return {"MAE": float(np.mean(np.abs(err))), "RMSE": float(np.sqrt(np.mean(err ** 2))), "MAPE_%": round(float(mape), 2)}


def run_forecast_compare(series: pd.Series, out_dir: Path) -> pd.DataFrame:
    train, test = series.iloc[:-TEST_HOURS], series.iloc[-TEST_HOURS:]
    horizon = len(test)
    preds = {
        "SeasonalNaive": seasonal_naive(train, horizon),
        "HoltWinters": fit_hw(train, horizon),
        "SARIMAX": fit_sarimax(train, horizon),
    }
    rows = [{"model": name, **metrics(test.to_numpy(), pred)} for name, pred in preds.items()]
    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "model_comparison.csv", index=False, encoding="utf-8-sig")

    fig, ax = plt.subplots(figsize=(14, 5))
    ax.plot(test.index, test.to_numpy(), "k-", lw=1.2, label="实际值")
    for (name, pred), color in zip(preds.items(), ["#999999", "#1f77b4", "#d62728"]):
        ax.plot(test.index, pred, color=color, lw=1.1, alpha=0.9, label=name)
    ax.set_title(f"问题1：预测对比（最后 {TEST_HOURS} 小时）")
    ax.set_xlabel("时间"); ax.set_ylabel("每小时事件数")
    ax.legend(); fig.tight_layout()
    fig.savefig(out_dir / "fig1_forecast.png", dpi=150)
    plt.close(fig)
    return df


# ---------------------------------------------------------------- 问题 2：异常检测
def stl_residuals(series: pd.Series) -> pd.Series:
    stl = STL(series, period=STL_PERIOD, robust=True)
    return stl.fit().resid


def merge_windows(flags: np.ndarray, index: pd.DatetimeIndex) -> list[dict]:
    """连续检出小时合并为异常窗口。"""
    windows, start = [], None
    for i, f in enumerate(flags):
        if f and start is None:
            start = i
        elif not f and start is not None:
            windows.append({"start": index[start], "end": index[i - 1], "hours": i - start})
            start = None
    if start is not None:
        windows.append({"start": index[start], "end": index[-1], "hours": len(index) - start})
    return windows


def dynamic_threshold_detect(resid: pd.Series, train_sigma: float, k: float, m: int) -> np.ndarray:
    """动态阈值：|残差| > k·σ，连续 m 小时确认。"""
    beyond = (resid.abs() > k * train_sigma).to_numpy()
    flags = np.zeros(len(resid), dtype=bool)
    run = 0
    for i, b in enumerate(beyond):
        run = run + 1 if b else 0
        if run >= m:
            flags[i - m + 1: i + 1] = True  # 确认后回填整段
    return flags


def isolation_forest_detect(series_df: pd.DataFrame, train_mask: np.ndarray, seed: int) -> np.ndarray:
    """多维检测：事件量、高危量、需人工量、OPEN 占比。

    contamination 按训练期预期的异常占比校准（正常时段约 2%），避免检出爆炸。
    """
    feats = ["total", "critical", "high", "requires_human", "open_ratio"]
    x = series_df[feats].to_numpy()
    model = IsolationForest(contamination=0.02, random_state=seed).fit(x[train_mask])
    return model.predict(x) == -1  # -1 为异常


def evaluate_windows(detected: list[dict], truth: pd.DataFrame, index: pd.DatetimeIndex, name: str) -> dict:
    """窗口级评估：TP=重叠窗口数，FP=无重叠检出，FN=漏检真值，延迟=首报时刻差。"""
    tp, delays = 0, []
    used = set()
    for _, t in truth.iterrows():
        matched = [i for i, d in enumerate(detected)
                   if d["start"] <= t["end"] and d["end"] >= t["start"] and i not in used]
        if matched:
            tp += 1
            first = min(matched, key=lambda i: detected[i]["start"])
            used.add(first)
            delay = max(0.0, (detected[first]["start"] - t["start"]).total_seconds() / 3600)
            delays.append(delay)
    fp = len(detected) - len(used)
    fn = len(truth) - tp
    recall = tp / len(truth) if len(truth) else 0.0
    precision = tp / len(detected) if detected else 0.0
    return {"detector": name, "检出窗口数": len(detected), "TP": tp, "FP": fp, "FN": fn,
            "精确率": round(precision, 3), "召回率": round(recall, 3),
            "平均预警延迟h": round(float(np.mean(delays)), 2) if delays else None}


def run_detection(series: pd.Series, series_df: pd.DataFrame, train_mask: np.ndarray,
                  truth: pd.DataFrame | None, out_dir: Path, seed: int) -> pd.DataFrame:
    resid = stl_residuals(series)
    train_sigma = float(resid[train_mask].std())
    flags_dt = dynamic_threshold_detect(resid, train_sigma, k=3.0, m=2)
    flags_if = isolation_forest_detect(series_df, train_mask, seed)
    flags_union = flags_dt | flags_if

    results, reports = [], {}
    for name, flags in [("动态阈值(k=3,m=2)", flags_dt),
                        ("IsolationForest", flags_if),
                        ("融合(取并集)", flags_union)]:
        wins = merge_windows(flags, series.index)
        reports[name] = wins
        if truth is not None and not truth.empty:
            results.append(evaluate_windows(wins, truth, series.index, name))

    # 窗口清单
    all_rows = []
    for name, wins in reports.items():
        for w in wins:
            all_rows.append({"detector": name, **{kk: (vv.isoformat(sep=" ", timespec="seconds")
                                                       if isinstance(vv, pd.Timestamp) else vv)
                                                  for kk, vv in w.items()}})
    pd.DataFrame(all_rows).to_csv(out_dir / "anomaly_report.csv", index=False, encoding="utf-8-sig")

    eval_df = pd.DataFrame(results) if results else pd.DataFrame()
    if not eval_df.empty:
        eval_df.to_csv(out_dir / "evaluation.csv", index=False, encoding="utf-8-sig")

    # 标注图：真值绿影、检出红影、动态阈值带
    fig, ax = plt.subplots(figsize=(15, 5))
    band = pd.DataFrame({"lo": series - 3 * train_sigma, "hi": series + 3 * train_sigma}, index=series.index)
    ax.fill_between(band.index, band["lo"], band["hi"], alpha=0.18, color="#1f77b4", label="±3σ 动态阈值带")
    ax.plot(series.index, series.to_numpy(), "k-", lw=0.8, label="事件量")
    for _, t in truth.iterrows():
        ax.axvspan(t["start"], t["end"], color="#2ca02c", alpha=0.20)
    for w in reports["融合(取并集)"]:
        ax.axvspan(w["start"], w["end"], color="#d62728", alpha=0.15, ymin=0.0, ymax=1.0)
    ax.set_title("问题2：异常检测（绿色=真值异常窗口，红色=检出窗口）")
    ax.set_xlabel("时间"); ax.set_ylabel("每小时事件数")
    ax.legend(); fig.tight_layout()
    fig.savefig(out_dir / "fig2_anomaly.png", dpi=150)
    plt.close(fig)
    return eval_df


# ---------------------------------------------------------------- 问题 3：阈值寻优 + CUSUM
def cusum_flags(resid: pd.Series, train_mean: float, train_sigma: float, h: float, drift: float = 0.5) -> np.ndarray:
    z = (resid - train_mean) / train_sigma
    s_pos = np.zeros(len(z))
    flags = np.zeros(len(z), dtype=bool)
    for i in range(1, len(z)):
        s_pos[i] = max(0.0, s_pos[i - 1] + z.iloc[i] - drift)
        flags[i] = s_pos[i] > h
    return flags


def run_optimization(series: pd.Series, train_mask: np.ndarray, truth: pd.DataFrame | None,
                     out_dir: Path) -> pd.DataFrame:
    resid = stl_residuals(series)
    mu, sigma = float(resid[train_mask].mean()), float(resid[train_mask].std())

    if truth is None or truth.empty:
        print("  无真值标注，跳过阈值寻优")
        return pd.DataFrame()

    rows = []
    for k in np.arange(1.5, 4.01, 0.25):
        for m in (1, 2, 3):
            flags = dynamic_threshold_detect(resid, sigma, float(k), m)
            wins = merge_windows(flags, series.index)
            r = evaluate_windows(wins, truth, series.index, f"k={k:.2f},m={m}")
            r["k"], r["m"] = round(float(k), 2), m
            r["cost"] = (COST_ALPHA * r["FP"] + COST_BETA * r["FN"]
                         + COST_GAMMA * (r["平均预警延迟h"] or 0.0))
            rows.append(r)
    grid = pd.DataFrame(rows)
    grid.to_csv(out_dir / "threshold_optimization.csv", index=False, encoding="utf-8-sig")
    best = grid.loc[grid["cost"].idxmin()]
    print(f"  最优组合：{best['detector']}  代价={best['cost']:.1f}  "
          f"(FP={best['FP']}, FN={best['FN']}, 延迟={best['平均预警延迟h']}h)")

    m_curve = grid[grid["m"] == 2]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(m_curve["k"], m_curve["cost"], "o-", color="#1f77b4")
    ax.set_title("问题3：代价函数寻优（m=2）\ncost = α·FP + β·FN + γ·延迟")
    ax.set_xlabel("阈值系数 k"); ax.set_ylabel("代价 cost")
    fig.tight_layout()
    fig.savefig(out_dir / "fig3_cost_curve.png", dpi=150)
    plt.close(fig)
    return grid


# ---------------------------------------------------------------- 主流程
def main():
    parser = argparse.ArgumentParser(description="方案一建模主流程")
    parser.add_argument("--data-dir", default=str(ROOT / "data" / "modeling-export-synthetic"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    out_dir = ROOT / "data" / "modeling-output" / "plan1"
    out_dir.mkdir(parents=True, exist_ok=True)

    series_df = pd.read_csv(data_dir / "hourly_event_series.csv", parse_dates=["created_at"])
    series = series_df.set_index("created_at")["total"].asfreq("h").fillna(0)
    truth_path = data_dir / "ground_truth_incidents.csv"
    truth = pd.read_csv(truth_path, parse_dates=["start", "end"]) if truth_path.exists() else pd.DataFrame()

    train_mask = np.arange(len(series)) < len(series) - TEST_HOURS
    print(f"数据：{data_dir.name}  共 {len(series)} 小时（训练 {int(train_mask.sum())} / 评估 {TEST_HOURS}）")
    if truth.empty:
        print("警告：无 ground_truth_incidents.csv，异常检测仅输出窗口清单，不做评估")

    print("\n[问题1] 三模型预测对比")
    cmp_df = run_forecast_compare(series, out_dir)
    print(cmp_df.to_string(index=False))

    print("\n[问题2] 异常检测与真值评估")
    eval_df = run_detection(series, series_df, train_mask, truth, out_dir, args.seed)
    if not eval_df.empty:
        print(eval_df.to_string(index=False))

    print("\n[问题3] 动态阈值寻优")
    run_optimization(series, train_mask, truth, out_dir)

    print(f"\n完成。图表与结果输出：{out_dir}")


if __name__ == "__main__":
    main()

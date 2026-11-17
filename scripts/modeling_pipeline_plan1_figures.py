# -*- coding: utf-8 -*-
"""
方案一补充图表：STL 分解与 ACF/PACF 定阶依据
============================================
读取 modeling_pipeline_plan1.py 使用的同一份数据，生成：
  fig4_stl_decomposition.png  STL 四分量分解图（观测 / 趋势 / 季节 / 残差）
  fig5_acf_pacf.png           一阶差分序列的 ACF / PACF（滞后 72 小时）
  stationarity_tests.csv      ADF 平稳性检验（原序列 / 一阶差分 / 季节差分）

用法：
  python scripts/modeling_pipeline_plan1_figures.py [--data-dir data/modeling-export-synthetic]
"""

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statsmodels.graphics.tsaplots import plot_acf, plot_pacf
from statsmodels.tsa.seasonal import STL
from statsmodels.tsa.stattools import adfuller

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

PERIOD = 24
MAX_LAG = 72
TEST_HOURS = 168  # 与主流程保持一致：最后 7 天为评估集


def plot_stl(series: pd.Series, out_path: Path):
    res = STL(series, period=PERIOD, robust=True).fit()
    fig, axes = plt.subplots(4, 1, figsize=(14, 9), sharex=True)
    parts = [
        (series, "观测值 $y_t$", "#333333"),
        (res.trend, "趋势项 $T_t$", "#1f77b4"),
        (res.seasonal, "季节项 $S_t$（周期=24h）", "#2ca02c"),
        (res.resid, "残差项 $R_t$", "#d62728"),
    ]
    for ax, (data, label, color) in zip(axes, parts):
        ax.plot(data.index, data.to_numpy(), color=color, lw=0.8)
        ax.set_ylabel(label, fontsize=9)
        ax.grid(alpha=0.25)
        if label.startswith("残差"):
            sigma = float(res.resid.std())
            ax.axhline(3 * sigma, color="#999999", ls="--", lw=0.9)
            ax.axhline(-3 * sigma, color="#999999", ls="--", lw=0.9)
            ax.text(data.index[5], 3 * sigma, " ±3σ", fontsize=8, color="#666666", va="bottom")
    axes[0].set_title("STL 加法分解：$y_t = T_t + S_t + R_t$", fontsize=12)
    axes[-1].set_xlabel("时间")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return res


def plot_acf_pacf(series: pd.Series, out_path: Path):
    diff = series.diff().dropna()
    fig, axes = plt.subplots(2, 1, figsize=(12, 7))
    plot_acf(diff, lags=MAX_LAG, ax=axes[0], alpha=0.05,
             title="自相关函数 ACF（一阶差分序列）")
    plot_pacf(diff, lags=MAX_LAG, ax=axes[1], alpha=0.05, method="ywm",
              title="偏自相关函数 PACF（一阶差分序列）")
    for ax in axes:
        for lag in (24, 48, 72):
            ax.axvline(lag, color="#f58518", ls=":", lw=0.9)
        ax.grid(alpha=0.2)
        ax.set_xlabel("滞后阶数（小时）")
    axes[0].text(24, axes[0].get_ylim()[1] * 0.85, " 24h", color="#f58518", fontsize=8)
    fig.suptitle("定阶依据：一阶差分序列的 ACF / PACF（虚线标注 24 小时季节周期）", fontsize=12)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return diff


def adf_row(name: str, data: pd.Series) -> dict:
    stat, pval, usedlag, nobs, crit, _ = adfuller(data.dropna(), autolag="AIC", result_object=False)
    return {
        "序列": name,
        "ADF统计量": round(float(stat), 4),
        "p值": round(float(pval), 4),
        "滞后阶数": int(usedlag),
        "样本量": int(nobs),
        "1%临界值": round(float(crit["1%"]), 4),
        "5%临界值": round(float(crit["5%"]), 4),
        "结论": "平稳" if pval < 0.05 else "非平稳",
    }


def cusum_stats(z: np.ndarray, drift: float = 0.5) -> tuple[np.ndarray, np.ndarray]:
    """双侧 CUSUM：分别累积正向与负向偏移，越过零即复位。"""
    s_pos = np.zeros(len(z))
    s_neg = np.zeros(len(z))
    for i in range(1, len(z)):
        s_pos[i] = max(0.0, s_pos[i - 1] + z[i] - drift)
        s_neg[i] = min(0.0, s_neg[i - 1] + z[i] + drift)
    return s_pos, s_neg


def alarm_episodes(flags: np.ndarray) -> list[int]:
    """将连续报警点合并为一次报警事件，返回各事件起始下标。"""
    starts = []
    prev = False
    for i, f in enumerate(flags):
        if f and not prev:
            starts.append(i)
        prev = f
    return starts


def evaluate_cusum(starts: list[int], index: pd.DatetimeIndex, truth: pd.DataFrame) -> dict:
    """报警事件与真值窗口配对：报警落在 [起始-2h, 结束+12h] 内即视为检出。"""
    delays, used = [], set()
    for _, t in truth.iterrows():
        lo, hi = t["start"] - pd.Timedelta(hours=2), t["end"] + pd.Timedelta(hours=12)
        hit = [i for i in starts if lo <= index[i] <= hi and i not in used]
        if hit:
            used.add(hit[0])
            delays.append((index[hit[0]] - t["start"]).total_seconds() / 3600)
    return {
        "报警次数": len(starts),
        "检出窗口数": len(used),
        "漏检数": len(truth) - len(used),
        "平均延迟h": round(float(np.mean(delays)), 2) if delays else None,
    }


def plot_cusum(series: pd.Series, resid: pd.Series, train_len: int,
               truth: pd.DataFrame | None, out_dir: Path):
    """图：上panel为原序列与真值窗口，下panel为双侧CUSUM统计量。"""
    mu = float(resid.iloc[:train_len].mean())
    sigma = float(resid.iloc[:train_len].std())
    z = ((resid - mu) / sigma).to_numpy()
    s_pos, s_neg = cusum_stats(z)
    index = series.index

    # 门限扫描：以报警事件数与检出窗口数权衡确定 h
    rows = []
    for h in (3, 4, 5, 6, 8, 10):
        starts = alarm_episodes((s_pos > h) | (s_neg < -h))
        row = {"门限h": h}
        if truth is not None and not truth.empty:
            row.update(evaluate_cusum(starts, index, truth))
        rows.append(row)
    sweep = pd.DataFrame(rows)
    if not sweep.empty:
        sweep.to_csv(out_dir / "cusum_threshold_sweep.csv", index=False, encoding="utf-8-sig")
    print(sweep.to_string(index=False))

    h = 5.0
    starts = alarm_episodes((s_pos > h) | (s_neg < -h))
    print(f"  采用门限 h={h}，报警事件 {len(starts)} 次")

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 7.5), sharex=True,
                                   gridspec_kw={"height_ratios": [1.15, 1]})
    ax1.plot(index, series.to_numpy(), color="#333333", lw=0.8, label="每小时事件数")
    if truth is not None and not truth.empty:
        for _, t in truth.iterrows():
            ax1.axvspan(t["start"], t["end"], color="#2ca02c", alpha=0.18)
        ax1.plot([], [], color="#2ca02c", alpha=0.35, lw=8, label="真值异常窗口")
    for i in starts:
        ax1.axvline(index[i], color="#d62728", ls=":", lw=1.0, alpha=0.8)
    ax1.set_ylabel("事件数")
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(alpha=0.25)
    ax1.set_title("CUSUM 变点检测：报警时刻与真实异常窗口的对应关系", fontsize=12)

    ax2.plot(index, s_pos, color="#1f77b4", lw=0.9, label="正向累积和 $s_t^+$")
    ax2.plot(index, s_neg, color="#d62728", lw=0.9, label="负向累积和 $s_t^-$")
    ax2.axhline(h, color="#666666", ls="--", lw=1.0)
    ax2.axhline(-h, color="#666666", ls="--", lw=1.0)
    ax2.text(index[5], h, f" 判决门限 h={h:g}", fontsize=8, color="#666666", va="bottom")
    for i in starts:
        v = s_pos[i] if s_pos[i] > h else s_neg[i]
        ax2.plot(index[i], v, marker="v", color="#ff7f0e", ms=6, zorder=5)
        ax2.annotate(f"{v:.1f}", (index[i], v), textcoords="offset points",
                     xytext=(6, -12), fontsize=8, color="#ff7f0e")
    if truth is not None and not truth.empty:
        for _, t in truth.iterrows():
            ax2.axvspan(t["start"], t["end"], color="#2ca02c", alpha=0.10)
    ax2.set_ylabel("CUSUM 统计量")
    ax2.set_xlabel("时间")
    ax2.legend(loc="lower left", fontsize=9)
    ax2.grid(alpha=0.25)

    fig.tight_layout()
    fig.savefig(out_dir / "fig6_cusum.png", dpi=150)
    plt.close(fig)
    return sweep


def main():
    parser = argparse.ArgumentParser(description="方案一补充图表")
    parser.add_argument("--data-dir", default=str(ROOT / "data" / "modeling-export-synthetic"))
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    out_dir = ROOT / "data" / "modeling-output" / "plan1"
    out_dir.mkdir(parents=True, exist_ok=True)

    src = data_dir / "hourly_event_series.csv"
    if not src.exists():
        raise SystemExit(f"缺少数据文件：{src}")
    series = (pd.read_csv(src, parse_dates=["created_at"])
              .set_index("created_at")["total"].asfreq("h").fillna(0))
    print(f"读取 {src}，共 {len(series)} 小时")

    print("\n[图4] STL 分解")
    res = plot_stl(series, out_dir / "fig4_stl_decomposition.png")
    var_share = {
        "趋势项": float(res.trend.var()),
        "季节项": float(res.seasonal.var()),
        "残差项": float(res.resid.var()),
    }
    total_var = sum(var_share.values())
    for k, v in var_share.items():
        print(f"  {k}方差占比：{v / total_var * 100:.1f}%")

    print("\n[图5] ACF / PACF（一阶差分，滞后 72h）")
    diff = plot_acf_pacf(series, out_dir / "fig5_acf_pacf.png")
    from statsmodels.tsa.stattools import acf, pacf
    a_vals, a_conf = acf(diff, nlags=MAX_LAG, alpha=0.05, result_object=False)
    p_vals, p_conf = pacf(diff, nlags=MAX_LAG, alpha=0.05, method="ywm", result_object=False)
    for lag in (1, 2, 3, 24, 48, 72):
        print(f"  lag={lag:2d}: ACF={a_vals[lag]:+.4f}  PACF={p_vals[lag]:+.4f}")
    sig = [lag for lag in range(1, MAX_LAG + 1)
           if abs(a_vals[lag]) > (a_conf[lag][1] - a_conf[lag][0]) / 2]
    print(f"  ACF 显著滞后：{sig[:12]}{' ...' if len(sig) > 12 else ''}")

    print("\n[ADF 平稳性检验]")
    tests = pd.DataFrame([
        adf_row("原序列", series),
        adf_row("一阶差分", series.diff()),
        adf_row("一阶+季节差分", series.diff().diff(PERIOD)),
    ])
    tests.to_csv(out_dir / "stationarity_tests.csv", index=False, encoding="utf-8-sig")
    print(tests.to_string(index=False))

    print("\n[图6] CUSUM 变点检测")
    truth_path = data_dir / "ground_truth_incidents.csv"
    truth = pd.read_csv(truth_path, parse_dates=["start", "end"]) if truth_path.exists() else None
    plot_cusum(series, res.resid, len(series) - TEST_HOURS, truth, out_dir)

    print(f"\n完成。输出：{out_dir}")


if __name__ == "__main__":
    main()

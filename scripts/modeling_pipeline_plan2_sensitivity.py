# -*- coding: utf-8 -*-
"""
方案二 灵敏度分析：OAT 扫描关键业务参数
====================================
参数对象（业务参数，而非模型超参数）：
  ① C     并发上限         2 / 3 / 4 / 5 / 6 / 8
  ② L     单次覆盖时长     2 / 3 / 4 / 6 / 8   （与 COVER 同义）
  ③ α     风险时段系数缩放 0.6 / 0.8 / 1.0 / 1.2 / 1.4
  ④ N     设备数量（规模） 18 / 24 / 30 / 36 / 42

指标：覆盖风险、覆盖率、贪心基线覆盖风险、相对贪心增益、最大盲区。
输出：
  sensitivity/raw.csv    —— 所有扫描点
  sensitivity/index.csv  —— 弹性系数 ΔZ/Δp
  sensitivity/summary.json
  sensitivity/fig1_response_curves.png
  sensitivity/fig2_tornado.png

用法：python scripts/modeling_pipeline_plan2_sensitivity.py [--seed 42] [--time-limit 30]
"""

import argparse
import json
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import modeling_pipeline_plan2 as p2

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

PARAM_KEYS = ["C", "L", "GAP", "N"]

SWEEPS = {
    "C":     [2, 3, 4, 5, 6, 8],
    "L":     [2, 3, 4, 6, 8],
    "GAP":   [2, 3, 4, 6, 8],
    "N":     [18, 20, 22, 24],
}

DEFAULT = {"C": 4, "L": 4, "GAP": 4, "N": 24}


# ---- 封装 MILP，支持参数覆盖 ---------------------------------------------
def solve_milp_with_params(targets: pd.DataFrame, R: np.ndarray, C_now: int,
                           cover_now: int, gap_now: int, time_limit: float = 30.0):
    """参数化 MILP：允许 C / COVER / GAP 动态覆盖。"""
    n = len(targets)
    nvar = 2 * n * p2.T
    dur = targets["duration"].to_numpy()
    visits = targets["visits"].to_numpy()
    wa = targets["window_start"].to_numpy()
    wb = targets["window_end"].to_numpy()

    def vy(i, t):
        return i * p2.T + t

    def vc(i, t):
        return n * p2.T + i * p2.T + t

    c = np.zeros(nvar)
    for i in range(n):
        for t in range(p2.T):
            c[vc(i, t)] = -R[i, t]

    rows, cols, vals, lows, ups = [], [], [], [], []
    nrow = [0]

    def add(coeffs, lo, hi):
        for j, v in coeffs:
            rows.append(nrow[0])
            cols.append(j)
            vals.append(v)
        lows.append(lo)
        ups.append(hi)
        nrow[0] += 1

    for i in range(n):
        add([(vy(i, t), 1.0) for t in range(p2.T)], visits[i], visits[i])
        for t1 in range(p2.T):
            for t2 in range(t1 + 1, min(p2.T, t1 + gap_now)):
                add([(vy(i, t1), 1.0), (vy(i, t2), 1.0)], -np.inf, 1.0)
        for t in range(p2.T):
            coeffs = [(vc(i, t), 1.0)]
            for s in range(max(0, t - cover_now + 1), t + 1):
                coeffs.append((vy(i, s), -1.0))
            add(coeffs, -np.inf, 0.0)

    for t in range(p2.T):
        coeffs = []
        for i in range(n):
            for s in range(max(0, t - int(dur[i]) + 1), t + 1):
                coeffs.append((vy(i, s), 1.0))
        add(coeffs, -np.inf, float(C_now))

    a_mat = coo_matrix((vals, (rows, cols)), shape=(nrow[0], nvar)).tocsr()

    ub = np.ones(nvar)
    for i in range(n):
        for t in range(p2.T):
            if t < wa[i] or t + dur[i] > wb[i]:
                ub[vy(i, t)] = 0.0

    res = milp(c=c, constraints=LinearConstraint(a_mat, np.array(lows), np.array(ups)),
               integrality=np.ones(nvar), bounds=Bounds(np.zeros(nvar), ub),
               options={"time_limit": time_limit})
    if res.x is None:
        return None
    x = np.round(res.x).astype(int)
    schedule = []
    for i in range(n):
        starts = [t for t in range(p2.T) if x[vy(i, t)] == 1]
        for k, t in enumerate(sorted(starts)):
            schedule.append({"target_index": i,
                             "target": targets.iloc[i]["target"],
                             "visit": k + 1, "start": int(t),
                             "end": int(t) + int(dur[i]),
                             "risk_weight": float(targets.iloc[i]["risk_weight"])})
    return schedule


# ---- 构造指定规模的实例 ---------------------------------------------------
def build_instance_n(seed: int, n_devices: int) -> pd.DataFrame:
    """基于原实例规则，按设备数量重新分配类别比例。"""
    rng = np.random.default_rng(seed)
    rows = []
    n_db = int(round(n_devices * 0.30))
    n_app = int(round(n_devices * 0.45))
    n_net = n_devices - n_db - n_app
    spec = [("db", n_db, (0, 8), 2, (3.0, 5.0), 2),
            ("app", n_app, (6, 22), 1, (1.5, 3.5), 2),
            ("net", n_net, (0, 24), 1, (1.0, 2.5), 2)]
    for cat, n, (a, b), dur, (wlo, whi), visits in spec:
        for k in range(1, n + 1):
            rows.append({"target": f"{cat}-{k:02d}", "category": cat,
                         "risk_weight": round(float(rng.uniform(wlo, whi)), 2),
                         "duration": dur, "visits": visits,
                         "window_start": a, "window_end": b,
                         "min_gap": p2.GAP})
    return pd.DataFrame(rows)


def compute_metrics(schedule: list[dict], targets: pd.DataFrame,
                    R: np.ndarray, cov_hours: int) -> dict:
    """用指定覆盖时长重新计算覆盖率（因为 MILP 里用的是 cov_hours，
    而原始 covered_risk 依赖全局 COVER 常量）。"""
    covered = np.zeros_like(R, dtype=bool)
    for s in schedule:
        lo = s["start"]
        hi = min(lo + cov_hours, p2.T)
        covered[s["target_index"], lo:hi] = True
    cov_amount = float(R[covered].sum())
    total = float(R.sum())
    # 贪心也要用同一套 R 和 cov_hours 评估
    order = p2.greedy_order(targets)
    g_sched, _ = p2.decode(order, targets)
    g_covered = np.zeros_like(R, dtype=bool)
    for s in g_sched:
        lo, hi = s["start"], min(s["start"] + cov_hours, p2.T)
        g_covered[s["target_index"], lo:hi] = True
    g_cov = float(R[g_covered].sum())

    gaps, weights = [], []
    for i, row in targets.iterrows():
        starts = sorted(s["start"] for s in schedule if s["target_index"] == i)
        edges = [0] + starts + [p2.T]
        gaps.append(max(edges[j + 1] - edges[j] for j in range(len(edges) - 1)))
        weights.append(float(row["risk_weight"]))
    gaps, weights = np.array(gaps), np.array(weights)

    return {
        "覆盖风险": round(cov_amount, 2),
        "覆盖率": round(cov_amount / total, 4) if total else 0,
        "贪心覆盖风险": round(g_cov, 2),
        "相对贪心增益%": round((cov_amount - g_cov) / g_cov * 100, 3) if g_cov else 0,
        "最大盲区h": round(float((gaps * weights).sum() / weights.sum()), 2),
    }


# ---- OAT 主循环 -----------------------------------------------------------
def run_oat(seed: int, time_limit: float) -> pd.DataFrame:
    rows = []
    base_targets = p2.build_instance(seed)
    base_R = p2.risk_matrix(base_targets)
    t0 = time.perf_counter()
    base_sched = solve_milp_with_params(base_targets, base_R, DEFAULT["C"],
                                        DEFAULT["L"], DEFAULT["GAP"], time_limit)
    if base_sched is None:
        raise SystemExit("基线 MILP 未解得可行解")
    base_m = compute_metrics(base_sched, base_targets, base_R, DEFAULT["L"])
    print(f"[基线] 覆盖率 {base_m['覆盖率']:.4f}，增益 {base_m['相对贪心增益%']:.2f}%，"
          f"耗时 {time.perf_counter() - t0:.2f}s")

    for key, values in SWEEPS.items():
        for v in values:
            if key == "C":
                targets, R = base_targets, base_R
                C_now, cov_hours, gap_now = int(v), DEFAULT["L"], DEFAULT["GAP"]
            elif key == "L":
                targets, R = base_targets, base_R
                C_now, cov_hours, gap_now = DEFAULT["C"], int(v), DEFAULT["GAP"]
            elif key == "GAP":
                # GAP 同时影响 MILP 约束和贪心评估的起始间隔，修改 instance
                targets = base_targets.assign(min_gap=int(v))
                R = p2.risk_matrix(targets)
                C_now, cov_hours, gap_now = DEFAULT["C"], DEFAULT["L"], int(v)
            elif key == "N":
                targets = build_instance_n(seed, int(v))
                R = p2.risk_matrix(targets)
                C_now, cov_hours, gap_now = DEFAULT["C"], DEFAULT["L"], DEFAULT["GAP"]
            else:
                continue

            t0 = time.perf_counter()
            sched = solve_milp_with_params(targets, R, C_now, cov_hours, gap_now, time_limit)
            elapsed = time.perf_counter() - t0
            if sched is None:
                rows.append({"参数": key, "取值": v, "覆盖风险": None, "覆盖率": None,
                             "贪心覆盖风险": None, "相对贪心增益%": None,
                             "最大盲区h": None, "耗时s": round(elapsed, 2), "可行": False})
                print(f"  {key}={v}: MILP 无可行解")
                continue
            m = compute_metrics(sched, targets, R, cov_hours)
            m.update({"耗时s": round(elapsed, 2), "可行": True, "参数": key, "取值": v})
            rows.append(m)
            print(f"  {key}={v}: 覆盖率 {m['覆盖率']:.4f}，增益 {m['相对贪心增益%']:.2f}%")
    return pd.DataFrame(rows)


# ---- 弹性系数与 Tornado ---------------------------------------------------
def build_index(raw: pd.DataFrame) -> pd.DataFrame:
    """对每个参数，在默认点附近计算弹性系数 = ΔZ/Z ÷ Δp/p。"""
    idx_rows = []
    for key in PARAM_KEYS:
        sub = raw[(raw["参数"] == key) & (raw["可行"].astype(bool))].copy()
        if sub.empty:
            continue
        p0 = DEFAULT[key]
        if not (sub["取值"] == p0).any():
            # 默认点无可行解，跳过该参数的弹性计算
            idx_rows.append({"参数": key, "C_弹性": None, "G_弹性": None, "B_弹性": None})
            continue
        z0_cov = float(sub[sub["取值"] == p0]["覆盖率"].iloc[0])
        z0_gain = float(sub[sub["取值"] == p0]["相对贪心增益%"].iloc[0])
        z0_blind = float(sub[sub["取值"] == p0]["最大盲区h"].iloc[0])

        def one_side(vals, z0_col, z0_val, sign_lo, sign_hi):
            elasticities = []
            lo = sub[(sub["取值"] < p0)].sort_values("取值", ascending=False).head(1)
            hi = sub[(sub["取值"] > p0)].sort_values("取值").head(1)
            if not lo.empty:
                p_lo, z_lo = float(lo["取值"].iloc[0]), float(lo[z0_col].iloc[0])
                elasticities.append(((z0_val - z_lo) / max(abs(z0_val), 1e-9))
                                    / ((p0 - p_lo) / max(abs(p0), 1e-9)) * sign_lo)
            if not hi.empty:
                p_hi, z_hi = float(hi["取值"].iloc[0]), float(hi[z0_col].iloc[0])
                elasticities.append(((z_hi - z0_val) / max(abs(z0_val), 1e-9))
                                    / ((p_hi - p0) / max(abs(p0), 1e-9)) * sign_hi)
            return float(np.mean(elasticities)) if elasticities else float("nan")

        # 覆盖率：正向更大更好，sign 均为 +1
        e_cov = one_side(None, "覆盖率", z0_cov, +1, +1)
        # 增益%：正向
        e_gain = one_side(None, "相对贪心增益%", z0_gain, +1, +1)
        # 盲区：负向更小更好 → 取反
        e_blind = one_side(None, "最大盲区h", z0_blind, -1, -1)

        idx_rows.append({"参数": key, "C_弹性": round(e_cov, 4),
                         "G_弹性": round(e_gain, 4), "B_弹性": round(e_blind, 4)})
    return pd.DataFrame(idx_rows)


# ---- 绘图 -----------------------------------------------------------------
def plot_response_curves(raw: pd.DataFrame, out_path: Path):
    fig, axes = plt.subplots(1, 4, figsize=(14, 3.8))
    param_labels = {"C": "并发上限 C", "L": "覆盖时长 L (h)",
                    "GAP": "最小间隔 GAP (h)", "N": "设备数量"}
    default_markers = DEFAULT

    for ax, key in zip(axes, PARAM_KEYS):
        sub = raw[(raw["参数"] == key) & (raw["可行"].astype(bool))].sort_values("取值")
        if sub.empty:
            ax.set_title(f"{param_labels.get(key, key)} (无可行解)", fontsize=10)
            ax.set_visible(True)
            continue
        p = sub["取值"].to_numpy()
        y_cov = sub["覆盖率"].to_numpy()
        y_gain = sub["相对贪心增益%"].to_numpy()
        ax.plot(p, y_cov, "o-", color="#1f77b4", label="覆盖率", lw=1.4, ms=5)
        ax.set_xlabel(param_labels.get(key, key))
        ax.set_ylabel("覆盖率", color="#1f77b4")
        ax.tick_params(axis="y", labelcolor="#1f77b4")
        ax.grid(alpha=0.25)
        ax2 = ax.twinx()
        ax2.plot(p, y_gain, "s--", color="#ff7f0e", label="增益%", lw=1.2, ms=4)
        ax2.set_ylabel("相对贪心增益 %", color="#ff7f0e")
        ax2.tick_params(axis="y", labelcolor="#ff7f0e")
        if key in default_markers:
            v0 = default_markers[key]
            if v0 in p:
                i0 = int(np.where(p == v0)[0][0])
                ax.plot(p[i0], y_cov[i0], "*", color="#d62728", ms=12, zorder=5)
                ax2.plot(p[i0], y_gain[i0], "*", color="#d62728", ms=12, zorder=5)
        # 标注不可行点
        infeas = raw[(raw["参数"] == key) & (~raw["可行"].astype(bool))]["取值"].tolist()
        if infeas:
            for v in infeas:
                ax.axvline(v, color="#cccccc", ls=":", lw=0.8)
                ax.text(v, ax.get_ylim()[1] * 0.95, "无可行解", fontsize=7,
                        ha="center", va="top", color="#999999", rotation=90)
        ax.set_title(param_labels.get(key, key), fontsize=10)
    fig.suptitle("响应曲线：覆盖率先看左轴蓝线，增益看右轴橙线（红 ★ 标记默认点）",
                 fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.92])
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_tornado(idx: pd.DataFrame, out_path: Path):
    """以 |C_弹性| 排序，画水平条形（Tornado 图简化版）。"""
    idx = idx[idx["C_弹性"].notna() & (idx["C_弹性"] != 0)].copy()
    idx_sorted = idx.reindex(idx["C_弹性"].abs().sort_values(ascending=True).index)
    labels = [{"C": "并发上限 C", "L": "覆盖时长 L",
               "GAP": "最小间隔 GAP", "N": "设备数量"}[k] for k in idx_sorted["参数"]]
    vals = idx_sorted["C_弹性"].to_numpy()
    fig, ax = plt.subplots(figsize=(7, 3.8))
    colors = ["#2ca02c" if v > 0 else "#d62728" for v in vals]
    y = np.arange(len(labels))
    ax.barh(y, vals, color=colors)
    ax.axvline(0, color="#333333", lw=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xlabel("覆盖风险弹性系数（%变化率 / %参数变化率）")
    ax.set_title("覆盖风险的参数敏感性排序（Tornado）", fontsize=11)
    ax.grid(axis="x", alpha=0.25)
    for i, v in enumerate(vals):
        ax.text(v + (0.01 if v >= 0 else -0.01), i, f"{v:+.3f}",
                va="center", ha="left" if v >= 0 else "right", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--time-limit", type=float, default=30.0)
    args = parser.parse_args()

    out_dir = ROOT / "data" / "modeling-output" / "plan2" / "sensitivity"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"灵敏度分析：OAT 扫描，time_limit={args.time_limit}s/点，seed={args.seed}")
    raw = run_oat(args.seed, args.time_limit)
    raw.to_csv(out_dir / "raw.csv", index=False, encoding="utf-8-sig")

    idx = build_index(raw[raw["参数"] != "base"])
    idx.to_csv(out_dir / "index.csv", index=False, encoding="utf-8-sig")
    print("\n弹性系数（默认点附近）：")
    print(idx.to_string(index=False))

    top = idx.reindex(idx["C_弹性"].abs().sort_values(ascending=False).index)
    summary = {
        "最敏感参数": top.iloc[0]["参数"],
        "最敏感弹性": round(float(top.iloc[0]["C_弹性"]), 4),
        "全部参数": top.to_dict(orient="records"),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                          encoding="utf-8")

    # 绘图（解耦：raw.csv 已落盘，重算即可）
    plot_response_curves(raw, out_dir / "fig1_response_curves.png")
    plot_tornado(idx, out_dir / "fig2_tornado.png")
    print(f"\n完成。输出：{out_dir}")


if __name__ == "__main__":
    main()

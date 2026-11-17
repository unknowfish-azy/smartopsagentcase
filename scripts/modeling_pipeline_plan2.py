# -*- coding: utf-8 -*-
"""
方案二主流程：巡检任务调度优化
==============================
场景：一天 24 个时段（1 小时/时段），对 N 台设备执行巡检。
平台约束：同时进行的巡检任务不超过 C=4 个（并发上限）。

每次巡检在完成后可覆盖其后 L 小时的"风险防护"，因此排班的核心不是"尽早巡检"，
而是"把有限的巡检能力放到风险最高的时段"。

模型（0-1 整数规划）：
  决策变量
    y_{i,t} ∈ {0,1}  设备 i 在时段 t 开始一次巡检
    c_{i,t} ∈ {0,1}  t 时刻设备 i 处于已巡检覆盖状态
  约束
    (1) 频次    Σ_t y_{i,t} = r_i
    (2) 时间窗  y_{i,t} = 0,  t ∉ [a_i, b_i - d_i]
    (3) 最小间隔 |t1 - t2| < g_i 时 y_{i,t1} + y_{i,t2} ≤ 1
    (4) 并发    Σ_i Σ_{s∈[t-d_i+1, t]} y_{i,s} ≤ C
    (5) 覆盖    c_{i,t} ≤ Σ_{s∈[t-L+1, t]} y_{i,s}
  目标
    max  Σ_i Σ_t R_{i,t} · c_{i,t},   R_{i,t} = w_i · p_cat(t)

其中 p_cat(t) 为类别风险时段系数：数据库类夜间高、应用类白天高、网络类全天平。

求解：
  - 贪心基线：按风险权重降序，逐个排到最早可行时段（模拟现有策略）；
  - 模拟退火：以任务优先序做排列编码，解码为最早可行排程；
  - 0-1 整数规划：scipy HiGHS 精确求解，作为最优性基准。

输出：data/modeling-output/plan2/
  - patrol_instance.csv     巡检实例（设备、风险、时长、频次、时间窗）
  - schedule_<solver>.csv   三种策略的排班表
  - comparison.csv          覆盖风险、完成率、加权巡检时刻、最大盲区
  - fig1_gantt.png          最优排班甘特图
  - fig2_convergence.png    模拟退火收敛曲线
  - fig3_metrics.png        三策略关键指标对比

用法：
  python scripts/modeling_pipeline_plan2.py [--seed 42] [--iters 4000]
"""

import argparse
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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

T = 24        # 时段数
C = 4         # 并发上限
GAP = 4       # 同一设备两次巡检最小间隔（小时）
COVER = 4     # 单次巡检的覆盖时长（小时）
BIG = 1e3     # 未排任务惩罚系数

# 类别风险时段系数：数据库夜间批处理风险高，应用类白天访问高峰风险高
PROFILE = {
    "db":  [1.8, 1.8, 1.7, 1.6, 1.5, 1.3, 1.0, 0.8, 0.6, 0.5, 0.5, 0.5,
            0.5, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.4, 1.6, 1.7, 1.8],
    "app": [0.4, 0.4, 0.4, 0.4, 0.5, 0.6, 0.8, 1.0, 1.3, 1.6, 1.8, 1.9,
            1.8, 1.9, 1.9, 1.8, 1.6, 1.4, 1.1, 0.9, 0.7, 0.6, 0.5, 0.4],
    "net": [1.0] * 24,
}


# ---------------------------------------------------------------- 实例构造
def build_instance(seed: int) -> pd.DataFrame:
    """构造 24 台设备的巡检实例。

    真实库中暂无巡检目标与时间窗数据，此处按平台业务语义设定：
      数据库类（夜间窗口，风险高）、应用类（白天窗口）、网络类（全天窗口）。
    """
    rng = np.random.default_rng(seed)
    rows = []
    spec = [("db", 7, (0, 8), 2, (3.0, 5.0), 2),
            ("app", 11, (6, 22), 1, (1.5, 3.5), 2),
            ("net", 6, (0, 24), 1, (1.0, 2.5), 2)]
    for cat, n, (a, b), dur, (wlo, whi), visits in spec:
        for k in range(1, n + 1):
            rows.append({
                "target": f"{cat}-{k:02d}",
                "category": cat,
                "risk_weight": round(float(rng.uniform(wlo, whi)), 2),
                "duration": dur,
                "visits": visits,
                "window_start": a,
                "window_end": b,
                "min_gap": GAP,
            })
    return pd.DataFrame(rows)


def risk_matrix(targets: pd.DataFrame) -> np.ndarray:
    """R[i, t] = 风险权重 × 类别时段系数。"""
    mat = np.zeros((len(targets), T))
    for i, row in targets.iterrows():
        mat[i] = np.array(PROFILE[row["category"]]) * float(row["risk_weight"])
    return mat


def task_list(targets: pd.DataFrame) -> list[tuple[int, int]]:
    tasks = []
    for i, row in targets.iterrows():
        for k in range(int(row["visits"])):
            tasks.append((i, k))
    return tasks


# ---------------------------------------------------------------- 排程解码
def decode(order: list[tuple[int, int]], targets: pd.DataFrame) -> tuple[list[dict], int]:
    """按优先序把任务依次排到最早可行时段；返回排班与未排任务数。"""
    occupancy = np.zeros(T)
    starts_of: dict[int, list[int]] = {}
    schedule, unscheduled = [], 0

    for i, k in order:
        row = targets.iloc[i]
        dur, a = int(row["duration"]), int(row["window_start"])
        b, gap = int(row["window_end"]), int(row["min_gap"])
        placed = False
        for t in range(a, b - dur + 1):
            if occupancy[t:t + dur].max() + 1 > C:
                continue
            if any(abs(t - s) < gap for s in starts_of.get(i, [])):
                continue
            occupancy[t:t + dur] += 1
            starts_of.setdefault(i, []).append(t)
            schedule.append({"target_index": i, "target": row["target"],
                             "visit": k + 1, "start": t, "end": t + dur,
                             "risk_weight": float(row["risk_weight"])})
            placed = True
            break
        if not placed:
            unscheduled += 1
    return schedule, unscheduled


def covered_risk(schedule: list[dict], R: np.ndarray) -> float:
    """按覆盖时长 COVER 统计被覆盖的风险量（同一时段只计一次）。"""
    covered = np.zeros_like(R, dtype=bool)
    for s in schedule:
        lo = s["start"]
        hi = min(lo + COVER, T)
        covered[s["target_index"], lo:hi] = True
    return float((R[covered]).sum())


def objective(schedule: list[dict], unscheduled: int, R: np.ndarray) -> float:
    """越小越好：负的覆盖风险 + 未排惩罚。"""
    return -covered_risk(schedule, R) + BIG * unscheduled


def greedy_order(targets: pd.DataFrame) -> list[tuple[int, int]]:
    """现有策略：风险权重降序，同权重按时间窗开始时刻升序。"""
    tasks = task_list(targets)
    return sorted(tasks, key=lambda tk: (-targets.iloc[tk[0]]["risk_weight"],
                                        targets.iloc[tk[0]]["window_start"], tk[1]))


# ---------------------------------------------------------------- 模拟退火
def simulated_annealing(targets, R, init, seed, iters=4000, t0=80.0):
    rng = np.random.default_rng(seed)
    cur = list(init)
    sched, uns = decode(cur, targets)
    cur_obj = objective(sched, uns, R)
    best, best_obj = list(cur), cur_obj
    history, temp = [], t0

    for it in range(iters):
        cand = list(cur)
        if rng.random() < 0.5:
            p, q = rng.integers(0, len(cand), 2)
            cand[p], cand[q] = cand[q], cand[p]
        else:
            p, q = sorted(rng.integers(0, len(cand), 2))
            cand[p:q + 1] = reversed(cand[p:q + 1])
        sched, uns = decode(cand, targets)
        obj = objective(sched, uns, R)
        delta = obj - cur_obj
        if delta <= 0 or rng.random() < np.exp(-delta / max(temp, 1e-9)):
            cur, cur_obj = cand, obj
            if obj < best_obj:
                best, best_obj = list(cand), obj
        temp *= 0.999 if it < iters * 0.7 else 0.9995
        temp = max(temp, 0.05)
        history.append(-best_obj)
    return best, best_obj, history


# ---------------------------------------------------------------- 整数规划
def solve_milp(targets: pd.DataFrame, R: np.ndarray):
    n = len(targets)
    nvar = 2 * n * T
    dur = targets["duration"].to_numpy()
    visits = targets["visits"].to_numpy()
    wa = targets["window_start"].to_numpy()
    wb = targets["window_end"].to_numpy()
    gap = targets["min_gap"].to_numpy()

    def vy(i, t):
        return i * T + t

    def vc(i, t):
        return n * T + i * T + t

    # 目标：最大化覆盖风险 → 最小化其相反数
    c = np.zeros(nvar)
    for i in range(n):
        for t in range(T):
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
        # 频次
        add([(vy(i, t), 1.0) for t in range(T)], visits[i], visits[i])
        # 最小间隔
        for t1 in range(T):
            for t2 in range(t1 + 1, min(T, t1 + int(gap[i]))):
                add([(vy(i, t1), 1.0), (vy(i, t2), 1.0)], -np.inf, 1.0)
        # 覆盖定义
        for t in range(T):
            coeffs = [(vc(i, t), 1.0)]
            for s in range(max(0, t - COVER + 1), t + 1):
                coeffs.append((vy(i, s), -1.0))
            add(coeffs, -np.inf, 0.0)

    # 并发
    for t in range(T):
        coeffs = []
        for i in range(n):
            for s in range(max(0, t - int(dur[i]) + 1), t + 1):
                coeffs.append((vy(i, s), 1.0))
        add(coeffs, -np.inf, float(C))

    a_mat = coo_matrix((vals, (rows, cols)), shape=(nrow[0], nvar)).tocsr()

    ub = np.ones(nvar)
    for i in range(n):
        for t in range(T):
            if t < wa[i] or t + dur[i] > wb[i]:
                ub[vy(i, t)] = 0.0

    t_start = time.perf_counter()
    res = milp(c=c, constraints=LinearConstraint(a_mat, np.array(lows), np.array(ups)),
               integrality=np.ones(nvar), bounds=Bounds(np.zeros(nvar), ub),
               options={"time_limit": 120})
    elapsed = time.perf_counter() - t_start
    if res.x is None:
        raise SystemExit(f"整数规划未求得可行解：{res.message}")

    x = np.round(res.x).astype(int)
    schedule = []
    for i in range(n):
        starts = [t for t in range(T) if x[vy(i, t)] == 1]
        for k, t in enumerate(sorted(starts)):
            schedule.append({"target_index": i, "target": targets.iloc[i]["target"],
                             "visit": k + 1, "start": int(t), "end": int(t) + int(dur[i]),
                             "risk_weight": float(targets.iloc[i]["risk_weight"])})
    return schedule, float(-res.fun), elapsed, res.message


# ---------------------------------------------------------------- 评价指标
def metrics_of(schedule, unscheduled, targets, R):
    total_tasks = int(targets["visits"].sum())
    done = len(schedule)
    covered = covered_risk(schedule, R)
    total = float(R.sum())

    wsum = sum(s["risk_weight"] for s in schedule) or 1.0
    weighted_start = sum(s["risk_weight"] * s["start"] for s in schedule) / wsum

    gaps, weights = [], []
    for i, row in targets.iterrows():
        starts = sorted(s["start"] for s in schedule if s["target_index"] == i)
        edges = [0] + starts + [T]
        gaps.append(max(edges[j + 1] - edges[j] for j in range(len(edges) - 1)))
        weights.append(float(row["risk_weight"]))
    gaps, weights = np.array(gaps), np.array(weights)

    return {
        "完成任务数": done,
        "任务总数": total_tasks,
        "完成率": round(done / total_tasks, 3),
        "未排任务数": unscheduled,
        "覆盖风险": round(covered, 1),
        "覆盖风险占比": round(covered / total, 4),
        "加权平均巡检时刻": round(float(weighted_start), 3),
        "风险加权最大盲区(h)": round(float((gaps * weights).sum() / weights.sum()), 2),
    }


# ---------------------------------------------------------------- 绘图
def plot_gantt(schedule, targets, out_path: Path):
    names = list(targets["target"])
    ypos = {n: j for j, n in enumerate(names)}
    risk = dict(zip(targets["target"], targets["risk_weight"]))
    cmap = plt.cm.YlOrRd
    rmin, rmax = min(risk.values()), max(risk.values())

    fig, ax = plt.subplots(figsize=(13, 7.6))
    for s in schedule:
        color = cmap((risk[s["target"]] - rmin) / max(rmax - rmin, 1e-9) * 0.7 + 0.2)
        ax.barh(ypos[s["target"]], s["end"] - s["start"], left=s["start"],
                height=0.6, color=color, edgecolor="#333333", lw=0.5)
        ax.text(s["start"] + (s["end"] - s["start"]) / 2, ypos[s["target"]],
                f"{s['start']}", ha="center", va="center", fontsize=7)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(0, T)
    ax.set_xticks(range(0, T + 1, 2))
    ax.set_xlabel("时段（小时）")
    ax.set_title(f"整数规划最优排班甘特图（并发上限 C={C}，色深表示风险权重）", fontsize=12)
    ax.grid(axis="x", alpha=0.3)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(rmin, rmax))
    fig.colorbar(sm, ax=ax, label="风险权重 $w_i$", fraction=0.025, pad=0.01)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_convergence(history, greedy_cov, milp_cov, out_path: Path):
    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.plot(history, color="#1f77b4", lw=1.4, label="模拟退火当前最优")
    ax.axhline(greedy_cov, color="#ff7f0e", ls="--", lw=1.2, label=f"贪心基线 {greedy_cov:.1f}")
    ax.axhline(milp_cov, color="#2ca02c", ls=":", lw=1.4, label=f"整数规划最优 {milp_cov:.1f}")
    ax.set_xlabel("迭代次数")
    ax.set_ylabel("覆盖风险总量")
    ax.set_title("模拟退火收敛曲线与最优性间隙", fontsize=12)
    ax.legend(fontsize=9)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_metrics(comp: pd.DataFrame, out_path: Path):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    colors = ["#ff7f0e", "#1f77b4", "#2ca02c"]
    for ax, col, title in [(axes[0], "覆盖风险占比", "风险覆盖率（越大越好）"),
                           (axes[1], "风险加权最大盲区(h)", "风险加权最大覆盖盲区（越小越好）")]:
        bars = ax.bar(comp["策略"], comp[col], color=colors)
        for b, v in zip(bars, comp[col]):
            ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.3f}" if v < 5 else f"{v:.1f}",
                    ha="center", va="bottom", fontsize=9)
        ax.set_title(title, fontsize=11)
        ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------- 主流程
def main():
    parser = argparse.ArgumentParser(description="方案二 巡检调度优化主流程")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--iters", type=int, default=4000)
    args = parser.parse_args()

    out_dir = ROOT / "data" / "modeling-output" / "plan2"
    out_dir.mkdir(parents=True, exist_ok=True)

    targets = build_instance(args.seed)
    targets.to_csv(out_dir / "patrol_instance.csv", index=False, encoding="utf-8-sig")
    R = risk_matrix(targets)
    print(f"巡检实例：{len(targets)} 台设备，任务总数 {int(targets['visits'].sum())}，"
          f"并发上限 C={C}，单时段容量 {T * C}，单次覆盖 {COVER}h")
    print(f"风险总量（所有设备所有时段）：{R.sum():.1f}")

    order_g = greedy_order(targets)
    sched_g, uns_g = decode(order_g, targets)
    m_g = metrics_of(sched_g, uns_g, targets, R)
    print(f"\n[贪心基线] 覆盖风险 {m_g['覆盖风险']}（{m_g['覆盖风险占比']:.2%}），完成率 {m_g['完成率']}")

    t0 = time.perf_counter()
    order_sa, _, history = simulated_annealing(targets, R, order_g, args.seed, args.iters)
    sa_time = time.perf_counter() - t0
    sched_sa, uns_sa = decode(order_sa, targets)
    m_sa = metrics_of(sched_sa, uns_sa, targets, R)
    print(f"[模拟退火] 覆盖风险 {m_sa['覆盖风险']}（{m_sa['覆盖风险占比']:.2%}），耗时 {sa_time:.1f}s")

    sched_m, cov_m, milp_time, msg = solve_milp(targets, R)
    m_m = metrics_of(sched_m, 0, targets, R)
    print(f"[整数规划] 覆盖风险 {m_m['覆盖风险']}（{m_m['覆盖风险占比']:.2%}），"
          f"耗时 {milp_time:.2f}s（{msg}）")

    for name, sched in [("greedy", sched_g), ("sa", sched_sa), ("milp", sched_m)]:
        pd.DataFrame(sched).sort_values(["target_index", "start"])[
            ["target", "visit", "start", "end", "risk_weight"]
        ].to_csv(out_dir / f"schedule_{name}.csv", index=False, encoding="utf-8-sig")

    comp = pd.DataFrame([
        {"策略": "贪心基线", **m_g, "求解耗时s": None},
        {"策略": "模拟退火", **m_sa, "求解耗时s": round(sa_time, 2)},
        {"策略": "整数规划", **m_m, "求解耗时s": round(milp_time, 3)},
    ])
    comp.to_csv(out_dir / "comparison.csv", index=False, encoding="utf-8-sig")

    gain_g = (m_m["覆盖风险"] - m_g["覆盖风险"]) / m_g["覆盖风险"] * 100
    gap_sa = (m_m["覆盖风险"] - m_sa["覆盖风险"]) / m_m["覆盖风险"] * 100
    print(f"\n整数规划相对贪心：覆盖风险提升 {gain_g:+.2f}%")
    print(f"模拟退火相对最优：差距 {gap_sa:.2f}%")
    print(comp[["策略", "覆盖风险占比", "完成率", "加权平均巡检时刻",
                "风险加权最大盲区(h)"]].to_string(index=False))

    plot_gantt(sched_m, targets, out_dir / "fig1_gantt.png")
    plot_convergence(history, m_g["覆盖风险"], m_m["覆盖风险"], out_dir / "fig2_convergence.png")
    plot_metrics(comp, out_dir / "fig3_metrics.png")
    print(f"\n完成。输出：{out_dir}")


if __name__ == "__main__":
    main()

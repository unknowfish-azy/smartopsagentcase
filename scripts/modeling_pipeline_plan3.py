# -*- coding: utf-8 -*-
"""
方案三主流程：执行闭环可靠性综合评价（AHP + 熵权法 + TOPSIS）
============================================================
对应技术路线三个问题：
  问题1 指标体系：从真实运行数据提炼 5 项二级指标（成功/性能/稳定维度）
  问题2 组合赋权：AHP 主观权重（一致性检验 CR<0.1）+ 熵权法客观权重
                  + 博弈论组合赋权（最小化组合与两者偏差）
  问题3 综合评价：TOPSIS 相对贴近度排序 + 四档等级评定
  附加   灵敏度分析：权重 ±10% 随机扰动 100 次，Kendall's tau 检验排序稳定性

评价对象（--scope）：
  model（默认）：模型连接（model_name），数据源 model_invocation_usage.csv
  tool         ：运维工具（tool_id），数据源 operation_run_record.csv

指标方向（+ 正向 / - 负向）：
  model: 成功率+、平均延迟-、P95延迟-、平均token-、延迟稳定性(CV)-
  tool : 成功率+、平均时长-、超时率-、调用频次+、时长稳定性(CV)-

输入：data/modeling-export-synthetic/（或 --data-dir 指向真实导出）
输出：data/modeling-output/plan3/
  - indicator_matrix.csv       原始指标矩阵
  - weights.csv                三种权重对比（AHP / 熵权 / 组合）
  - topsis_result.csv          贴近度、排名、等级
  - sensitivity.csv            扰动实验中每个对象的排名稳定性
  - fig1_weights.png           主客观权重对比
  - fig2_topsis.png            TOPSIS 贴近度与等级
  - fig3_sensitivity.png       排名稳定性

用法：
  python scripts/modeling_pipeline_plan3.py [--scope model|tool] [--data-dir ...] [--seed 42]
"""

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import kendalltau

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

# 指标定义：(列名, 中文名, 方向 +1 正向 / -1 负向)
INDICATORS = {
    "model": [
        ("success_rate", "成功率", +1),
        ("avg_duration_ms", "平均延迟", -1),
        ("p95_duration_ms", "P95延迟", -1),
        ("avg_total_tokens", "平均Token", -1),
        ("cv_duration", "延迟稳定性", -1),
    ],
    "tool": [
        ("success_rate", "成功率", +1),
        ("avg_duration_s", "平均时长", -1),
        ("timeout_rate", "超时率", -1),
        ("run_count", "调用频次", +1),
        ("cv_duration", "时长稳定性", -1),
    ],
}

# AHP 判断矩阵（1~9 标度），行/列顺序与 INDICATORS 一致
AHP_MATRICES = {
    "model": np.array([
        [1.0,   3.0,   2.0,   4.0,   5.0],
        [1 / 3, 1.0,   1 / 2, 2.0,   2.0],
        [1 / 2, 2.0,   1.0,   3.0,   3.0],
        [1 / 4, 1 / 2, 1 / 3, 1.0,   1.0],
        [1 / 5, 1 / 2, 1 / 3, 1.0,   1.0],
    ]),
    "tool": np.array([
        [1.0,   3.0,   2.0,   5.0,   4.0],
        [1 / 3, 1.0,   1 / 2, 2.0,   2.0],
        [1 / 2, 2.0,   1.0,   3.0,   3.0],
        [1 / 5, 1 / 2, 1 / 3, 1.0,   1.0],
        [1 / 4, 1 / 2, 1 / 3, 1.0,   1.0],
    ]),
}

RI_TABLE = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45}
GRADE_BANDS = [(0.8, "优"), (0.6, "良"), (0.4, "中"), (0.0, "差")]


# ---------------------------------------------------------------- 问题1：指标矩阵
def build_indicator_matrix(data_dir: Path, scope: str) -> pd.DataFrame:
    """从原始明细聚合出「对象 × 指标」矩阵，每个对象一行。"""
    if scope == "model":
        path = data_dir / "model_invocation_usage.csv"
        if not path.exists():
            raise SystemExit(f"缺少数据文件：{path}")
        df = pd.read_csv(path, parse_dates=["started_at"])
        if df.empty:
            raise SystemExit("model_invocation_usage 无数据，无法评价")
        df["ok"] = df["status"].str.upper().isin(["SUCCESS", "OK", "COMPLETED"])
        grouped = df.groupby("model_name")
        matrix = pd.DataFrame({
            "success_rate": grouped["ok"].mean(),
            "avg_duration_ms": grouped["duration_ms"].mean(),
            "p95_duration_ms": grouped["duration_ms"].quantile(0.95),
            "avg_total_tokens": grouped["total_tokens"].mean(),
            "cv_duration": grouped["duration_ms"].std() / grouped["duration_ms"].mean(),
        })
        matrix.index.name = "对象"
    else:
        path = data_dir / "operation_run_record.csv"
        if not path.exists():
            raise SystemExit(f"缺少数据文件：{path}")
        df = pd.read_csv(path, parse_dates=["started_at", "ended_at"])
        if df.empty:
            raise SystemExit("operation_run_record 无数据，无法评价")
        df["ok"] = df["status"].str.upper().isin(["SUCCESS", "OK", "COMPLETED"])
        df["timeout"] = df["status"].str.upper().eq("TIMEOUT")
        df["duration_s"] = (df["ended_at"] - df["started_at"]).dt.total_seconds().clip(lower=0)
        grouped = df.groupby("tool_id")
        matrix = pd.DataFrame({
            "success_rate": grouped["ok"].mean(),
            "avg_duration_s": grouped["duration_s"].mean(),
            "timeout_rate": grouped["timeout"].mean(),
            "run_count": grouped.size(),
            "cv_duration": grouped["duration_s"].std() / grouped["duration_s"].mean(),
        })
        matrix.index.name = "对象"
    # 稳定性指标可能因单一取值产生 NaN/无穷，按最差处理避免整行失效
    return matrix.fillna(matrix.max()).replace([np.inf, -np.inf], np.nan).fillna(0.0)


# ---------------------------------------------------------------- 问题2：AHP 权重
def ahp_weights(matrix: np.ndarray) -> tuple[np.ndarray, float, float]:
    """特征向量法求权重 + 一致性检验。返回 (权重, λmax, CR)。"""
    n = matrix.shape[0]
    eigvals, eigvecs = np.linalg.eig(matrix)
    idx = int(np.argmax(eigvals.real))
    lam_max = float(eigvals[idx].real)
    w = np.abs(eigvecs[:, idx].real)
    w = w / w.sum()
    ci = (lam_max - n) / (n - 1) if n > 1 else 0.0
    cr = ci / RI_TABLE[n] if RI_TABLE.get(n, 0) > 0 else 0.0
    return w, lam_max, cr


# ---------------------------------------------------------------- 问题2：熵权法
def entropy_weights(norm: np.ndarray) -> np.ndarray:
    """熵权法：norm 为已正向化到 [0,1] 的矩阵（行=对象，列=指标）。"""
    eps = 1e-6
    x = norm + eps
    p = x / x.sum(axis=0, keepdims=True)
    n = x.shape[0]
    e = -(p * np.log(p)).sum(axis=0) / np.log(n)
    d = 1.0 - e
    return d / d.sum() if d.sum() > 0 else np.full(x.shape[1], 1.0 / x.shape[1])


def game_theory_combine(w_ahp: np.ndarray, w_ent: np.ndarray) -> np.ndarray:
    """博弈论组合赋权：解 (W W^T) a = diag(W W^T)，再归一化线性组合系数。"""
    w = np.vstack([w_ahp, w_ent])
    gram = w @ w.T
    rhs = np.diag(gram)
    try:
        a = np.linalg.solve(gram, rhs)
    except np.linalg.LinAlgError:
        a = np.array([0.5, 0.5])
    a = np.abs(a)
    if a.sum() == 0:
        a = np.array([0.5, 0.5])
    a = a / a.sum()
    combined = a[0] * w_ahp + a[1] * w_ent
    return combined / combined.sum(), a


def forward_normalize(matrix: pd.DataFrame, indicators: list) -> np.ndarray:
    """极差归一化：负向指标反向，全部映射到 [0,1]。"""
    x = matrix[[c for c, _, _ in indicators]].to_numpy(dtype=float)
    lo, hi = x.min(axis=0), x.max(axis=0)
    span = np.where(hi - lo == 0, 1.0, hi - lo)
    norm = (x - lo) / span
    for j, (_, _, direction) in enumerate(indicators):
        if direction < 0:
            norm[:, j] = 1.0 - norm[:, j]
    return norm


# ---------------------------------------------------------------- 问题3：TOPSIS
def topsis(norm: np.ndarray, weights: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """向量归一化 → 加权 → 正负理想解 → 相对贴近度。"""
    denom = np.sqrt((norm ** 2).sum(axis=0))
    denom = np.where(denom == 0, 1.0, denom)
    weighted = (norm / denom) * weights
    ideal_best, ideal_worst = weighted.max(axis=0), weighted.min(axis=0)
    d_best = np.sqrt(((weighted - ideal_best) ** 2).sum(axis=1))
    d_worst = np.sqrt(((weighted - ideal_worst) ** 2).sum(axis=1))
    closeness = d_worst / np.where(d_best + d_worst == 0, 1.0, d_best + d_worst)
    return closeness, d_best, d_worst


def grade_of(score: float) -> str:
    for threshold, label in GRADE_BANDS:
        if score >= threshold:
            return label
    return "差"


# ---------------------------------------------------------------- 附加：灵敏度分析
def sensitivity_analysis(norm: np.ndarray, weights: np.ndarray, base_rank: np.ndarray,
                         seed: int, rounds: int = 100) -> pd.DataFrame:
    """权重独立 ±10% 随机扰动，计算扰动排名与原排名的 Kendall's tau。"""
    rng = np.random.default_rng(seed)
    n_obj = norm.shape[0]
    taus, rank_hits = [], np.zeros((rounds, n_obj), dtype=int)
    for r in range(rounds):
        perturbed = weights * rng.uniform(0.9, 1.1, size=len(weights))
        perturbed = perturbed / perturbed.sum()
        score, _, _ = topsis(norm, perturbed)
        ranks = (-score).argsort().argsort() + 1
        rank_hits[r] = ranks
        tau = kendalltau(base_rank, ranks).statistic
        taus.append(1.0 if np.isnan(tau) else float(tau))
    stability = (rank_hits == base_rank[None, :]).mean(axis=0)
    return pd.DataFrame({
        "对象": range(n_obj),
        "原始排名": base_rank,
        "排名保持不变比例": np.round(stability, 3),
    }), np.array(taus)


# ---------------------------------------------------------------- 主流程
def main():
    parser = argparse.ArgumentParser(description="方案三 综合评价主流程")
    parser.add_argument("--scope", choices=["model", "tool"], default="model")
    parser.add_argument("--data-dir", default=str(ROOT / "data" / "modeling-export-synthetic"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    # 按 scope 分目录，避免 model / tool 两次运行互相覆盖
    out_dir = ROOT / "data" / "modeling-output" / "plan3" / args.scope
    out_dir.mkdir(parents=True, exist_ok=True)
    indicators = INDICATORS[args.scope]

    print(f"[问题1] 构建指标矩阵（scope={args.scope}）")
    matrix = build_indicator_matrix(data_dir, args.scope)
    if len(matrix) < 2:
        raise SystemExit(f"有效评价对象仅 {len(matrix)} 个，至少需要 2 个才能做 TOPSIS")
    matrix.to_csv(out_dir / "indicator_matrix.csv", encoding="utf-8-sig")
    print(matrix.round(4).to_string())
    print(f"评价对象 {len(matrix)} 个，指标 {len(indicators)} 项")

    print("\n[问题2] 组合赋权")
    norm = forward_normalize(matrix, indicators)
    w_ahp, lam_max, cr = ahp_weights(AHP_MATRICES[args.scope])
    print(f"  AHP：λmax={lam_max:.4f}，CR={cr:.4f} -> {'通过' if cr < 0.1 else '未通过（需调整判断矩阵）'}")
    if cr >= 0.1:
        raise SystemExit("AHP 一致性检验未通过，请调整 AHP_MATRICES")
    w_ent = entropy_weights(norm)
    w_comb, coeff = game_theory_combine(w_ahp, w_ent)
    print(f"  组合系数：AHP={coeff[0]:.3f}，熵权={coeff[1]:.3f}")

    names = [c for _, c, _ in indicators]
    weight_df = pd.DataFrame({
        "指标": [n for _, n, _ in indicators],
        "方向": ["正向" if d > 0 else "负向" for _, _, d in indicators],
        "AHP权重": np.round(w_ahp, 4),
        "熵权法权重": np.round(w_ent, 4),
        "组合权重": np.round(w_comb, 4),
    })
    weight_df.to_csv(out_dir / "weights.csv", index=False, encoding="utf-8-sig")
    print(weight_df.to_string(index=False))

    print("\n[问题3] TOPSIS 综合评价")
    closeness, d_best, d_worst = topsis(norm, w_comb)
    order = (-closeness).argsort()
    rank = np.empty(len(closeness), dtype=int)
    rank[order] = np.arange(1, len(closeness) + 1)
    result = pd.DataFrame({
        "对象": matrix.index,
        "D+": np.round(d_best, 4),
        "D-": np.round(d_worst, 4),
        "贴近度C": np.round(closeness, 4),
        "排名": rank,
    })
    result["等级"] = result["贴近度C"].apply(grade_of)
    result = result.sort_values("排名").reset_index(drop=True)
    result.to_csv(out_dir / "topsis_result.csv", index=False, encoding="utf-8-sig")
    print(result.to_string(index=False))

    print("\n[附加] 灵敏度分析（权重 ±10% 扰动 ×100）")
    sens, taus = sensitivity_analysis(norm, w_comb, rank, args.seed)
    sens["对象"] = matrix.index[sens["对象"]]
    sens.to_csv(out_dir / "sensitivity.csv", index=False, encoding="utf-8-sig")
    print(f"  Kendall's tau：均值 {taus.mean():.3f}，最小值 {taus.min():.3f}，"
          f"标准差 {taus.std():.3f}")
    print(f"  排序结论：{'稳定' if taus.min() >= 0.8 else '存在波动，需在论文中说明'}")

    # ------------------------------------------------------------ 图表
    fig, ax = plt.subplots(figsize=(10, 5))
    idx = np.arange(len(names))
    width = 0.26
    ax.bar(idx - width, w_ahp, width, label="AHP 主观权重", color="#4c78a8")
    ax.bar(idx, w_ent, width, label="熵权法客观权重", color="#f58518")
    ax.bar(idx + width, w_comb, width, label="博弈论组合权重", color="#54a24b")
    ax.set_xticks(idx)
    ax.set_xticklabels([n for _, n, _ in indicators])
    ax.set_ylabel("权重")
    ax.set_title("问题2：主客观权重对比")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "fig1_weights.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 4.5))
    colors = {"优": "#54a24b", "良": "#4c78a8", "中": "#f58518", "差": "#d62728"}
    bars = ax.barh(result["对象"][::-1], result["贴近度C"][::-1],
                   color=[colors[g] for g in result["等级"][::-1]])
    for b, (name, val, g) in zip(bars, zip(result["对象"][::-1], result["贴近度C"][::-1], result["等级"][::-1])):
        ax.text(val + 0.01, b.get_y() + b.get_height() / 2, f"{val:.3f} ({g})", va="center", fontsize=9)
    for thr, _ in GRADE_BANDS[:-1]:
        ax.axvline(thr, color="#999999", ls="--", lw=0.8)
    ax.set_xlim(0, 1.05)
    ax.set_xlabel("相对贴近度 C")
    ax.set_title("问题3：TOPSIS 综合评价结果")
    fig.tight_layout()
    fig.savefig(out_dir / "fig2_topsis.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar(range(len(taus)), np.sort(taus), color="#4c78a8")
    ax.axhline(0.8, color="#d62728", ls="--", lw=1, label="稳定性阈值 0.8")
    ax.set_xlabel("扰动实验序号（按 tau 升序）")
    ax.set_ylabel("Kendall's tau")
    ax.set_title("附加：权重扰动下排序稳定性")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "fig3_sensitivity.png", dpi=150)
    plt.close(fig)

    print(f"\n完成。结果与图表输出：{out_dir}")


if __name__ == "__main__":
    main()

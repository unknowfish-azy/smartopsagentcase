# -*- coding: utf-8 -*-
"""
方案三补充图表
==============
读取 modeling_pipeline_plan3.py 已产出的结果文件，生成论文用的补充图表：
  fig4_hierarchy.png    指标体系层级图（目标层 → 准则层 → 指标层）
  fig5_ahp_matrix.png   AHP 判断矩阵热力图（对数色阶 + 分数标注）
  fig6_ideal_distance.png  TOPSIS 正/负理想解距离对比
  fig7_radar.png        各对象归一化指标雷达图
  ahp_consistency.csv   一致性检验表（λmax / CI / RI / CR）

前置：先运行 scripts/modeling_pipeline_plan3.py --scope <scope>

用法：
  python scripts/modeling_pipeline_plan3_figures.py [--scope model|tool]
"""

import sys
from fractions import Fraction
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyBboxPatch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from modeling_pipeline_plan3 import (  # noqa: E402
    AHP_MATRICES,
    INDICATORS,
    RI_TABLE,
    ahp_weights,
    forward_normalize,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

# 二级指标 → 一级准则的归属（与 INDICATORS 的列名对应）
HIERARCHY = {
    "model": [
        ("执行可靠性", ["success_rate"]),
        ("响应性能", ["avg_duration_ms", "p95_duration_ms"]),
        ("资源效率", ["avg_total_tokens"]),
        ("稳定韧性", ["cv_duration"]),
    ],
    "tool": [
        ("执行可靠性", ["success_rate", "timeout_rate"]),
        ("响应性能", ["avg_duration_s"]),
        ("负载承载", ["run_count"]),
        ("稳定韧性", ["cv_duration"]),
    ],
}

COLOR_GOAL = "#1f4e79"
COLOR_CRIT = "#4c78a8"
COLOR_IND = "#9ecae1"


def draw_box(ax, x, y, w, h, text, facecolor, fontsize=10, textcolor="white"):
    box = FancyBboxPatch((x - w / 2, y - h / 2), w, h,
                         boxstyle="round,pad=0.008,rounding_size=0.012",
                         linewidth=1.0, edgecolor="#ffffff", facecolor=facecolor, zorder=2)
    ax.add_patch(box)
    ax.text(x, y, text, ha="center", va="center", fontsize=fontsize,
            color=textcolor, zorder=3, wrap=True)


def plot_hierarchy(scope: str, out_path: Path):
    """三层指标体系：目标层 → 准则层 → 指标层。"""
    crit_def = HIERARCHY[scope]
    ind_name = {code: label for code, label, _ in INDICATORS[scope]}
    n_ind = sum(len(v) for _, v in crit_def)

    fig, ax = plt.subplots(figsize=(11, 1.05 * max(n_ind, 4) + 1.2))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    x_goal, x_crit, x_ind = 0.10, 0.40, 0.72
    # 指标层纵向均匀分布
    ind_ys, cursor = {}, 1 - 1.0 / (n_ind + 1)
    step = 1.0 / (n_ind + 1)

    # 准则层位置取其所辖指标的中心
    crit_ys, y = {}, cursor
    for crit, codes in crit_def:
        ys = []
        for _ in codes:
            ys.append(y)
            y -= step
        crit_ys[crit] = float(np.mean(ys))
        for code, yy in zip(codes, ys):
            ind_ys[code] = yy

    goal_y = 0.5
    draw_box(ax, x_goal, goal_y, 0.17, 0.16, "执行闭环可靠性\n综合评价", COLOR_GOAL, 11)

    for crit, _ in crit_def:
        cy = crit_ys[crit]
        draw_box(ax, x_crit, cy, 0.15, 0.11, crit, COLOR_CRIT, 10)
        ax.plot([x_goal + 0.085, x_crit - 0.075], [goal_y, cy], color="#666666", lw=1.0, zorder=1)

    for crit, codes in crit_def:
        for code in codes:
            iy = ind_ys[code]
            draw_box(ax, x_ind, iy, 0.16, 0.10, ind_name[code], COLOR_IND, 10, textcolor="#1a1a1a")
            ax.plot([x_crit + 0.075, x_ind - 0.08], [crit_ys[crit], iy], color="#999999", lw=0.9, zorder=1)

    ax.text(0.10, 0.97, "目标层", ha="center", fontsize=11, color="#333333")
    ax.text(0.40, 0.97, "准则层", ha="center", fontsize=11, color="#333333")
    ax.text(0.72, 0.97, "指标层", ha="center", fontsize=11, color="#333333")
    ax.set_title(f"执行闭环可靠性评价指标体系（scope={scope}）", fontsize=12, pad=6)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def fraction_label(v: float) -> str:
    return str(Fraction(v).limit_denominator(9))


def plot_ahp_matrix(scope: str, out_path: Path):
    """AHP 判断矩阵热力图：对数色阶让互反元素对称，标注原始分数。"""
    matrix = AHP_MATRICES[scope]
    labels = [name for _, name, _ in INDICATORS[scope]]
    n = len(labels)
    logm = np.log10(matrix)

    fig, ax = plt.subplots(figsize=(7.2, 6.0))
    im = ax.imshow(logm, cmap="RdBu_r", vmin=-np.abs(logm).max(), vmax=np.abs(logm).max())
    for i in range(n):
        for j in range(n):
            txt = fraction_label(matrix[i, j])
            color = "white" if abs(logm[i, j]) > 0.35 else "#222222"
            ax.text(j, i, txt, ha="center", va="center", fontsize=11, color=color, fontweight="bold")
    ax.set_xticks(range(n))
    ax.set_xticklabels(labels, rotation=20, ha="right")
    ax.set_yticks(range(n))
    ax.set_yticklabels(labels)
    ax.set_xticks(np.arange(-0.5, n, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, n, 1), minor=True)
    ax.grid(which="minor", color="white", lw=1.2)
    ax.tick_params(which="minor", length=0)
    fig.colorbar(im, ax=ax, label="log10(判断值)", fraction=0.046, pad=0.04)
    ax.set_title(f"AHP 判断矩阵（1~9 标度，scope={scope}）", fontsize=12, pad=10)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_ideal_distance(result: pd.DataFrame, out_path: Path):
    """TOPSIS 正/负理想解距离对比：D- 越大越好，D+ 越小越好。"""
    df = result.sort_values("排名", ascending=False)
    y = np.arange(len(df))
    fig, ax = plt.subplots(figsize=(9, 0.9 * len(df) + 2.0))
    ax.barh(y + 0.18, df["D+"], height=0.34, color="#d62728", label="D+ 到正理想解（越小越好）")
    ax.barh(y - 0.18, df["D-"], height=0.34, color="#2ca02c", label="D- 到负理想解（越大越好）")
    for i, (dp, dm, c) in enumerate(zip(df["D+"], df["D-"], df["贴近度C"])):
        ax.text(dp + 0.008, i + 0.18, f"{dp:.3f}", va="center", fontsize=8.5)
        ax.text(dm + 0.008, i - 0.18, f"{dm:.3f}", va="center", fontsize=8.5)
        ax.text(max(dp, dm) + 0.09, i, f"C={c:.3f}", va="center", fontsize=9, color="#333333")
    ax.set_yticks(y)
    ax.set_yticklabels(df["对象"])
    ax.set_xlabel("加权欧氏距离")
    ax.set_xlim(0, max(df["D+"].max(), df["D-"].max()) * 1.45)
    ax.set_title("TOPSIS 正/负理想解距离对比", fontsize=12, pad=10)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=2, fontsize=9, frameon=False)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_radar(indicators_matrix: pd.DataFrame, norm: np.ndarray, scope: str, out_path: Path):
    """雷达图：所有指标已正向归一化，越靠外越好。"""
    labels = [f"{name}\n({'正向' if d > 0 else '负向'})" for _, name, d in INDICATORS[scope]]
    n = len(labels)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(7.2, 6.4), subplot_kw={"polar": True})
    colors = plt.cm.tab10(np.linspace(0, 1, len(indicators_matrix)))
    for name, row, color in zip(indicators_matrix.index, norm, colors):
        vals = np.round(np.asarray(row, dtype=float), 3).tolist()
        vals += vals[:1]
        ax.plot(angles, vals, "o-", lw=1.6, color=color, label=str(name), markersize=4)
        ax.fill(angles, vals, color=color, alpha=0.08)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylim(0, 1.05)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0.25", "0.5", "0.75", "1.0"], fontsize=8)
    ax.set_title("各评价对象归一化指标雷达图", fontsize=12, pad=18)
    ax.legend(loc="upper right", bbox_to_anchor=(1.28, 1.12), fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="方案三补充图表")
    parser.add_argument("--scope", choices=["model", "tool"], default="model")
    args = parser.parse_args()

    out_dir = ROOT / "data" / "modeling-output" / "plan3" / args.scope
    need = ["indicator_matrix.csv", "topsis_result.csv"]
    missing = [f for f in need if not (out_dir / f).exists()]
    if missing:
        raise SystemExit(f"缺少结果文件 {missing}，请先运行：python scripts/modeling_pipeline_plan3.py --scope {args.scope}")

    matrix = pd.read_csv(out_dir / "indicator_matrix.csv", index_col=0)
    result = pd.read_csv(out_dir / "topsis_result.csv")
    norm = forward_normalize(matrix, INDICATORS[args.scope])

    print(f"读取 {out_dir}")
    print(f"对象 {len(matrix)} 个，指标 {len(INDICATORS[args.scope])} 项")

    print("\n[图4] 指标体系层级图")
    plot_hierarchy(args.scope, out_dir / "fig4_hierarchy.png")

    print("[图5] AHP 判断矩阵热力图")
    plot_ahp_matrix(args.scope, out_dir / "fig5_ahp_matrix.png")

    print("[图6] TOPSIS 正负理想解距离")
    plot_ideal_distance(result, out_dir / "fig6_ideal_distance.png")

    print("[图7] 归一化指标雷达图")
    plot_radar(matrix, norm, args.scope, out_dir / "fig7_radar.png")

    # 一致性检验表
    w, lam_max, cr = ahp_weights(AHP_MATRICES[args.scope])
    n = len(w)
    ci = (lam_max - n) / (n - 1)
    consistency = pd.DataFrame([{
        "scope": args.scope,
        "矩阵阶数n": n,
        "最大特征根λmax": round(lam_max, 4),
        "一致性指标CI": round(ci, 4),
        "平均随机一致性RI": RI_TABLE[n],
        "一致性比率CR": round(cr, 4),
        "结论": "通过" if cr < 0.1 else "未通过",
    }])
    consistency.to_csv(out_dir / "ahp_consistency.csv", index=False, encoding="utf-8-sig")
    print("\n[AHP 一致性检验]")
    print(consistency.to_string(index=False))

    print(f"\n完成。补充图表输出：{out_dir}")


if __name__ == "__main__":
    main()

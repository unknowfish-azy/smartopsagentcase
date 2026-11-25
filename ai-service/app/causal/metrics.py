# -*- coding: utf-8 -*-
"""P2-7 / C 的评测指标纯函数（骨架）。

全部复用仓库既有的统计层 ``scripts/stats_inference.py``（Wilson / 分层 bootstrap /
配对 McNemar / Holm / ICC / DEFF），**不新造统计实现**。

⚠️ 这里只算「给定记录下的指标」。**记录从哪来**（C1 干预构造 / C2 配对构造）
尚未实现，见 ``ai-service/scripts/build_counterfactual.py``。

口径要点（§4.5 C-G3 / §4.6 风险 2）：
- 单看 ``flip_rate`` 会被平凡规则刷满 → 必须与 **误伤率** 一起报告；
- 任一分母为 0 一律 ``NOT_RUN``，不得记 0、不得记「已达标」；
- 增益只在 **Holm 校正后显著** 且区间不含 0 时才可写「有增益」。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Sequence

from .schema import FlipRecord, MetricResult, PairVerdict

REPO = Path(__file__).resolve().parents[3]          # <repo>/ai-service/app/causal -> <repo>
STATS_DIR = REPO / "scripts"
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _stats() -> Any:
    """惰性导入既有统计层；缺失时给出可操作的报错，而不是静默降级。"""

    try:
        import scripts.stats_inference as stats  # type: ignore
    except Exception as exc:  # pragma: no cover - 环境缺失时才触发
        raise RuntimeError(
            "无法导入 scripts.stats_inference（仓库布局变动？）。"
            f"因果评测必须复用既有统计层，不得另写一套：{exc}"
        ) from exc
    return stats


def _judged(records: Sequence[FlipRecord], *, true_root: bool) -> list[FlipRecord]:
    return [r for r in records if r.is_true_root is true_root and r.flipped is not None]


def flip_rate(records: Sequence[FlipRecord]) -> MetricResult:
    """C1 主指标：对**真根因节点**干预后 top-1 是否离开原判。"""

    judged = _judged(records, true_root=True)
    if not judged:
        return MetricResult(
            name="counterfactual_flip_rate", value=None, n=0, status="NOT_RUN",
            note="无「干预真根因且前后均可判定」的记录；不得记 0",
        )
    hits = sum(1 for r in judged if r.flipped)
    low, high = _stats().wilson_interval(hits, len(judged))
    return MetricResult(
        name="counterfactual_flip_rate", value=round(hits / len(judged), 6),
        n=len(judged), status="COMPLETED", wilson_95=(low, high),
        note="仅描述生成器下的改判比例，须与 collateral_flip_rate 同时引用",
    )


def collateral_flip_rate(records: Sequence[FlipRecord]) -> MetricResult:
    """误伤率：对**非根因节点**干预时是否也改判（越高越说明模型并未抓住因果特征）。"""

    judged = _judged(records, true_root=False)
    if not judged:
        return MetricResult(
            name="collateral_flip_rate", value=None, n=0, status="NOT_RUN",
            note="无非根因干预记录；此时 flip_rate 不可单独解释",
        )
    hits = sum(1 for r in judged if r.flipped)
    low, high = _stats().wilson_interval(hits, len(judged))
    return MetricResult(
        name="collateral_flip_rate", value=round(hits / len(judged), 6),
        n=len(judged), status="COMPLETED", wilson_95=(low, high),
        note="误伤率与 flip_rate 差距越大，越支持「响应针对因果特征」",
    )


def pair_accuracy(verdicts: Sequence[PairVerdict]) -> MetricResult:
    """C2 主指标：配对中真根因被排在前面的比例。"""

    if not verdicts:
        return MetricResult(
            name="pair_accuracy", value=None, n=0, status="NOT_RUN",
            note="无配对判定记录（C2 生成器未实现）",
        )
    hits = sum(1 for v in verdicts if v.preferred_correct)
    low, high = _stats().wilson_interval(hits, len(verdicts))
    return MetricResult(
        name="pair_accuracy", value=round(hits / len(verdicts), 6),
        n=len(verdicts), status="COMPLETED", wilson_95=(low, high),
        note="配对已消除拓扑难度差异，但仍是合成生成器下的相对度量",
    )


def compare_models(
    causal_hits: Sequence[bool],
    corr_hits: Sequence[bool],
    *,
    alpha: float = 0.05,
    n_boot: int = 5000,
    seed: int | None = None,
) -> dict[str, Any]:
    """A@1 增益：因果变体 vs 相关模型（C-G3 的唯一判据）。

    配对输入（同一 scenario/seed/event）。返回 ``status``：
    ``COMPLETED``（可检验）/ ``NOT_RUN``（b+c=0 无可检验差异）/ ``INSUFFICIENT_DATA``。
    """

    stats = _stats()
    a = [bool(x) for x in causal_hits]
    b = [bool(x) for x in corr_hits]
    if len(a) != len(b) or not a:
        return {
            "name": "a1_gain", "value": None, "n": 0, "status": "INSUFFICIENT_DATA",
            "note": "两模型记录必须等长且非空",
        }
    n = len(a)
    n_only_causal = sum(1 for x, y in zip(a, b) if x and not y)   # b（McNemar 命名）
    n_only_corr = sum(1 for x, y in zip(a, b) if y and not x)     # c
    gain = (sum(a) - sum(b)) / n

    interval = stats.bootstrap_difference_interval(
        [float(x) for x in a], [float(y) for y in b],
        statistic=lambda v: sum(v) / len(v), paired=True,
        n_resamples=n_boot, confidence=1.0 - alpha, method="percentile", seed=seed,
    )
    ci_low = interval.get("ci_low")
    ci_high = interval.get("ci_high")

    # 先判「无可检验差异」：此时 mcnemar 的 p_value 为 None，
    # 若仍喂给 Holm 校正会直接 TypeError（骨架期实测踩到）。
    if n_only_causal + n_only_corr == 0:
        return {
            "name": "a1_gain",
            "value": round(gain, 6),
            "n": n,
            "status": "NOT_RUN",
            "ci_low": ci_low,
            "ci_high": ci_high,
            "excludes_zero": bool(interval.get("excludes_zero")),
            "b_only_causal": 0,
            "c_only_corr": 0,
            "mcnemar_p": None,
            "holm_adjusted_p": None,
            "significant_after_holm": False,
            "note": "两模型逐样本完全一致（b=c=0）→ 无可检验差异，不得记 p=1",
        }

    mc = stats.mcnemar_test(n_only_causal, n_only_corr, alpha=alpha)
    # 注意：holm_bonferroni 返回 dict（含 ``items``），不是 list——
    # 早期骨架写成 ``[0]`` 会直接 KeyError，导致整个评测崩溃。
    holm_item = stats.holm_bonferroni(
        [mc["p_value"]], alpha=alpha, labels=["a1_gain"]
    )["items"][0]
    holm_p = holm_item["adjusted_p"]

    return {
        "name": "a1_gain",
        "value": round(gain, 6),
        "n": n,
        "status": "COMPLETED",
        "ci_low": ci_low,
        "ci_high": ci_high,
        "excludes_zero": bool(interval.get("excludes_zero")),
        "b_only_causal": n_only_causal,
        "c_only_corr": n_only_corr,
        "mcnemar_p": mc.get("p_value"),
        "holm_adjusted_p": holm_p,
        "significant_after_holm": bool(
            holm_p is not None and holm_p < alpha
            and ci_low is not None and ci_high is not None
            and (ci_low > 0 or ci_high < 0)
        ),
        "note": "Holm 校正后显著且区间不含 0 才可写「有增益」",
    }


def effective_n(groups: Sequence[Sequence[float]]) -> dict[str, Any]:
    """C-G4：按 M30 的 ICC(1)/DEFF 口径给有效样本量，不得用名义 n 撑区间。

    ⚠️ 早期骨架读 ``icc["m"]``，但 ``icc_one_way`` **不返回** ``m``（只返回
    ``k_groups`` / ``n_total`` / ``m0``）→ 取值恒为 1.0 → DEFF 恒等于 1 →
    有效 n 恒等于名义 n，C-G4 形同虚设。这里改用**平均组大小**计算。
    """

    stats = _stats()
    icc = stats.icc_one_way(groups)
    n_total = int(icc.get("n_total") or sum(len(g) for g in groups))
    k_groups = int(icc.get("k_groups") or len(groups))
    avg_group_size = (n_total / k_groups) if k_groups else 1.0
    icc_value = float(icc.get("icc") or 0.0)

    if icc.get("status") != "COMPLETED":
        # 分组数 < 2 等情形：不给虚假的 DEFF，直接标注不可解释。
        return {
            "n_total": n_total,
            "n_groups": k_groups,
            "avg_group_size": round(avg_group_size, 6),
            "icc": icc.get("icc"),
            "icc_status": icc.get("status"),
            "deff": None,
            "effective_n": None,
            "note": f"ICC 不可计算（{icc.get('reason', icc.get('status'))}），"
                    "有效 n 记 NOT_RUN，禁止用名义 n 撑区间",
        }

    deff = stats.design_effect(avg_group_size, icc_value)
    return {
        "n_total": n_total,
        "n_groups": k_groups,
        "avg_group_size": round(avg_group_size, 6),
        "icc": icc.get("icc"),
        "icc_status": icc.get("status"),
        "deff": round(deff, 6),
        "effective_n": round(stats.effective_n(n_total, deff), 4),
    }


__all__ = [
    "flip_rate",
    "collateral_flip_rate",
    "pair_accuracy",
    "compare_models",
    "effective_n",
]

"""P2-7 / C2 + C4：反事实评测与统计收口（**仅骨架**）。

方案：``docs/design/p2-7-causal-kg-debate-v1/DESIGN.md`` §4.4（C2/C4）、
§4.5（C-G3/C-G4）、§5（统一禁止事项）。

本脚本**只消费记录、不生成样本**：
- ``flip_rate`` / ``collateral_flip_rate``（C1，须一起看，否则平凡规则可刷满）；
- ``pair_accuracy``（C2 配对）；
- ``a1_gain``（因果变体 vs 相关模型；Holm 校正后显著才可写「增益」）；
- ``effective_n``（ICC/DEFF，禁止用名义 n 撑区间）。

统计一律复用 ``scripts/stats_inference.py``，**不新造实现**。

⚠️ **当前状态（2026-11-24）**：上游 ``build_counterfactual.py`` 的生成器未实现，
因此正常运行下所有指标都是 ``NOT_RUN``（骨架预期行为），报告必须照实写。

用法：::

    python ai-service/scripts/eval_counterfactual.py \
        --flips data/counterfactual/flips.jsonl \
        --pairs data/counterfactual/pairs_verdicts.jsonl \
        --causal-hits hits_causal.json --corr-hits hits_corr.json \
        --report reports/counterfactual.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

AI_SERVICE = Path(__file__).resolve().parents[1]
REPO_ROOT = AI_SERVICE.parent
for _path in (str(AI_SERVICE), str(REPO_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from app.causal import metrics as cm  # noqa: E402
from app.causal.schema import FlipRecord, PairVerdict  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LOOP_DISCLOSURE = (
    "合成数据的因果结构由生成器给定（C-G2 / M29 口径⑦）：本报告只说明模型在该"
    "生成器下的相对优劣，不得外推为生产因果推断。"
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                rows.append(json.loads(text))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"[error] {path}:{line_no} 不是合法 JSON：{exc}") from exc
    return rows


def load_hits(path: Path | None) -> list[bool] | None:
    """读模型逐样本命中（true/false 数组）；未指定路径返回 None（→ NOT_RUN）。"""

    if path is None:
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not all(isinstance(x, bool) for x in raw):
        raise SystemExit(f"[error] {path} 必须是 true/false 数组")
    return [bool(x) for x in raw]


def evaluate(
    *,
    flips: Sequence[dict[str, Any]] | None,
    pair_verdicts: Sequence[dict[str, Any]] | None,
    causal_hits: Sequence[bool] | None,
    corr_hits: Sequence[bool] | None,
    alpha: float,
    n_boot: int,
    seed: int | None,
) -> dict[str, Any]:
    """汇总全部指标；缺数据一律 NOT_RUN，不伪造 0。"""

    flip_records = [FlipRecord(**row) for row in (flips or [])]
    verdicts = [PairVerdict(**row) for row in (pair_verdicts or [])]

    result: dict[str, Any] = {
        "counterfactual_flip_rate": cm.flip_rate(flip_records).to_dict(),
        "collateral_flip_rate": cm.collateral_flip_rate(flip_records).to_dict(),
        "pair_accuracy": cm.pair_accuracy(verdicts).to_dict(),
    }

    if causal_hits is None or corr_hits is None:
        result["a1_gain"] = {
            "name": "a1_gain", "value": None, "n": 0, "status": "NOT_RUN",
            "note": "未提供两模型逐样本命中 → 无可检验差异（禁止记 p=1 或 0）",
        }
    else:
        result["a1_gain"] = cm.compare_models(
            causal_hits, corr_hits, alpha=alpha, n_boot=n_boot, seed=seed,
        )

    return result


def render_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    add = lines.append

    add("# EXP-CF-001 · 反事实评测（P2-7 / C）")
    add("")
    add(f"> 运行：{payload['created_at']} ｜ 状态：{payload['status']}")
    add("")
    add(f"> ⚠️ **循环披露（C-G2）**：{LOOP_DISCLOSURE}")
    add("")
    add("## 指标")
    add("")
    add("| 指标 | 值 | n | 状态 | Wilson 95% |")
    add("|---|---|---|---|---|")
    for key in ("counterfactual_flip_rate", "collateral_flip_rate", "pair_accuracy"):
        item = payload["metrics"][key]
        value = "null" if item["value"] is None else f"{item['value']:.4f}"
        ci = item.get("wilson_95")
        add(f"| {key} | {value} | {item['n']} | {item['status']} | "
            f"{'—' if not ci else f'[{ci[0]:.4f}, {ci[1]:.4f}]'} |")
    gain = payload["metrics"]["a1_gain"]
    add(f"| a1_gain | {'null' if gain['value'] is None else f'{gain['value']:.4f}'} | "
        f"{gain['n']} | {gain['status']} | "
        f"{'—' if gain.get('ci_low') is None else f'[{gain['ci_low']:.4f}, {gain['ci_high']:.4f}]'} |")
    add("")
    add("## 有效样本量（C-G4）")
    add("")
    eff = payload["effective_n"]
    add(f"- 名义 n={eff['n_total']}、分组 {eff['n_groups']}、"
        f"平均组大小 {eff.get('avg_group_size')}、ICC={eff.get('icc')}、"
        f"DEFF={eff.get('deff')} → 有效 n={eff.get('effective_n')}")
    if eff.get("note"):
        add(f"- ⚠️ {eff['note']}")
    add("")
    add("## 禁止事项（沿用 §5 与口径⑲）")
    add("")
    add("1. **禁止**写「因果训练提升准确率 X%」——除非 `a1_gain` 在 Holm 校正后显著且区间不含 0，"
        "否则一律写「未证明增益」。")
    add("2. **禁止**只看 `flip_rate`——必须与误伤率 `collateral_flip_rate` 同时报告"
        "（单看可被「总是改判」的平凡规则刷满）。")
    add("3. **禁止**用名义 n 撑区间；有效 n 缺失时相关结论不可解释。")
    add("4. **禁止**把合成生成器下的结论写成生产因果推断。")
    add("")
    add("## 复现")
    add("")
    add("```bash")
    add("# 上游生成器（骨架，未实现）：")
    add("python ai-service/scripts/build_counterfactual.py --scenario <s> --model <m> "
        "--seed 20261125 --n-events 200 --out data/counterfactual/card.json")
    add("# 评测：")
    add("python ai-service/scripts/eval_counterfactual.py --report reports/counterfactual.json")
    add("```")
    add("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P2-7/C 反事实评测（骨架）")
    parser.add_argument("--flips", type=Path, default=None, help="C1 干预记录 JSONL")
    parser.add_argument("--pairs", type=Path, default=None, help="C2 配对判定 JSONL")
    parser.add_argument("--causal-hits", type=Path, default=None, help="因果变体逐样本命中 JSON")
    parser.add_argument("--corr-hits", type=Path, default=None, help="相关模型逐样本命中 JSON")
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--n-boot", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--groups", type=Path, default=None,
                        help="分组 JSON（数组的数组，每组为逐样本命中 0/1）→ C-G4 有效 n；"
                             "不提供则有效 n 记 NOT_RUN")
    parser.add_argument("--report", type=Path, required=True, help="报告输出（.json）")
    args = parser.parse_args(argv)

    # 指定了路径就必须存在：把「跑错路径」静默当成 NOT_RUN 是最危险的失败模式。
    for label, path in (("--flips", args.flips), ("--pairs", args.pairs),
                        ("--causal-hits", args.causal_hits), ("--corr-hits", args.corr_hits)):
        if path is not None and not path.exists():
            print(f"[error] {label} 指向的文件不存在：{path}")
            return 2

    flips = read_jsonl(args.flips) if args.flips else None
    pair_rows = read_jsonl(args.pairs) if args.pairs else None
    causal_hits = load_hits(args.causal_hits)
    corr_hits = load_hits(args.corr_hits)

    metrics = evaluate(
        flips=flips, pair_verdicts=pair_rows,
        causal_hits=causal_hits, corr_hits=corr_hits,
        alpha=args.alpha, n_boot=args.n_boot, seed=args.seed,
    )

    # C-G4：有效样本量按「分组」计算；无分组信息时显式 NOT_RUN。
    if args.groups:
        groups_raw = json.loads(args.groups.read_text(encoding="utf-8"))
        if not isinstance(groups_raw, list) or not all(
            isinstance(g, list) for g in groups_raw
        ):
            print(f"[error] --groups 必须是「数组的数组」：{args.groups}")
            return 2
        effective = cm.effective_n([[float(v) for v in g] for g in groups_raw])
    else:
        effective = cm.effective_n([])

    completed = [k for k, v in metrics.items() if v.get("status") == "COMPLETED"]
    status = "COMPLETED" if completed else "NOT_RUN"
    payload = {
        "experiment_id": "EXP-CF-001",
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "loop_disclosure": LOOP_DISCLOSURE,
        "inputs": {
            "flips": str(args.flips) if args.flips else None,
            "pairs": str(args.pairs) if args.pairs else None,
            "causal_hits": str(args.causal_hits) if args.causal_hits else None,
            "corr_hits": str(args.corr_hits) if args.corr_hits else None,
        },
        "metrics": metrics,
        "effective_n": effective,
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    md_path = args.report.with_suffix(".md")
    md_path.write_text(render_markdown(payload), encoding="utf-8")

    print(f"[ok] 状态={status} 已完成指标={completed or '无'}")
    print(f"[ok] {args.report} / {md_path}")
    if status == "NOT_RUN":
        print("[warn] 全部 NOT_RUN 属骨架预期：上游生成器未实现，禁止据此下任何结论。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

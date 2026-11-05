"""Inspector ablation: how much does each check level actually contribute?

Four configurations on the same frozen fixture (50 cases, labels never enter
the prediction path):

    A full        L1 rule + L2 evidence + L3 ai + L4 state verifier
    B no_l4       L1 + L2 + L3 only
    C all_off     nothing runs (lower bound)
    D l4_only     L4 state verifier only

Nothing in agent/inspector/ is modified; levels are switched off by injecting
no-op collaborators into InspectorPipeline's documented constructor parameters.

Usage:
    python scripts/eval_inspector_ablation.py
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from agent.inspector.pipeline import InspectorPipeline  # noqa: E402
from scripts.eval_false_success import load_cases, predict  # noqa: E402

DEFAULT_OUTPUT = REPO_ROOT / "06-工程整改/eval_inspector_ablation.csv"
GROUPS = ("A_full", "B_no_l4", "C_all_off", "D_l4_only")


class _NoOpJudge:
    """Stand-in for a disabled check level: reports nothing."""

    def check(self, context: dict[str, Any]) -> list:
        return []


class _NoOpStateVerifier:
    """Stand-in for a disabled L4.

    ``checked=False`` matters: it means "unknown", and the evaluator excludes
    unknown observations from the binary denominator rather than silently
    counting them as "no false success".
    """

    def verify(self, agent_claim, actual_state):
        return {
            "checked": False,
            "false_success": False,
            "reason": "L4 disabled in ablation",
            "actual_state": {},
        }

    def check(self, context: dict[str, Any]) -> list:
        return []


def build_pipeline(group: str) -> InspectorPipeline:
    if group == "A_full":
        return InspectorPipeline()
    if group == "B_no_l4":
        return InspectorPipeline(state_verifier=_NoOpStateVerifier())
    if group == "C_all_off":
        return InspectorPipeline(
            rule_judge=_NoOpJudge(),
            evidence_judge=_NoOpJudge(),
            ai_judge=_NoOpJudge(),
            state_verifier=_NoOpStateVerifier(),
        )
    if group == "D_l4_only":
        return InspectorPipeline(
            rule_judge=_NoOpJudge(),
            evidence_judge=_NoOpJudge(),
            ai_judge=_NoOpJudge(),
        )
    raise ValueError(f"unknown group: {group}")


def score(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [r for r in rows if r["expected_false_success"] is not None]
    tp = sum(r["expected_false_success"] is True and r["detected_false_success"] for r in scored)
    tn = sum(r["expected_false_success"] is False and not r["detected_false_success"] for r in scored)
    fp = sum(r["expected_false_success"] is False and r["detected_false_success"] for r in scored)
    fn = sum(r["expected_false_success"] is True and not r["detected_false_success"] for r in scored)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "scored_n": len(scored), "TP": tp, "TN": tn, "FP": fp, "FN": fn,
        "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
    }


def evaluate(output_csv: str | Path = DEFAULT_OUTPUT) -> dict[str, dict[str, Any]]:
    cases = load_cases()
    rows: list[dict[str, Any]] = []
    summary: dict[str, dict[str, Any]] = {}

    for group in GROUPS:
        pipeline = build_pipeline(group)
        group_rows: list[dict[str, Any]] = []
        for case in cases:
            result = predict(case, pipeline)
            verification = result.verification_result or {}
            row = {
                "group": group,
                "sample_id": case["id"],
                "category": case["category"],
                "probe_shape": json.dumps(case["probes"], ensure_ascii=False),
                "expected_false_success": case["expected_false_success"],
                "detected_false_success": bool(verification.get("false_success")),
                "l4_checked": verification.get("checked") is True,
                "inspection_status": result.status.value,
                "reason": verification.get("reason"),
            }
            group_rows.append(row)
            rows.append(row)
        metrics = score(group_rows)
        # per-category recall, computed only over positively labelled cases
        by_cat: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for r in group_rows:
            if r["expected_false_success"] is True:
                by_cat[r["category"]][1] += 1
                by_cat[r["category"]][0] += int(r["detected_false_success"])
        metrics["per_category"] = {
            cat: f"{hit}/{total}" for cat, (hit, total) in sorted(by_cat.items())
        }
        metrics["status_distribution"] = dict(Counter(r["inspection_status"] for r in group_rows))
        summary[group] = metrics

    output = Path(output_csv)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    summary = evaluate(args.output)

    print(f"{'group':<12}{'scored':>7}{'TP':>4}{'TN':>4}{'FP':>4}{'FN':>4}"
          f"{'P':>8}{'R':>8}{'F1':>8}")
    for group in GROUPS:
        m = summary[group]
        print(f"{group:<12}{m['scored_n']:>7}{m['TP']:>4}{m['TN']:>4}{m['FP']:>4}{m['FN']:>4}"
              f"{m['precision']:>8.4f}{m['recall']:>8.4f}{m['f1']:>8.4f}")

    print("\nper-category recall (hit/total, positives only):")
    cats = sorted(summary["A_full"]["per_category"])
    print(f"{'category':<24}" + "".join(f"{g:>12}" for g in GROUPS))
    for cat in cats:
        print(f"{cat:<24}" + "".join(f"{summary[g]['per_category'].get(cat, '-'):>12}" for g in GROUPS))

    print("\nstatus distribution:")
    for group in GROUPS:
        print(f"  {group:<12}{summary[group]['status_distribution']}")

    print(f"\nCSV: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

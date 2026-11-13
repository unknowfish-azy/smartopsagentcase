"""M05 人工盲评汇总：各维度均分 + 两两 Cohen's κ。

输入为长表 CSV（不含任何 AI 生成的评分，评分必须来自真人评者）：
    sample_id,rater,dimension,score
    S01,R1,usefulness,4

用法：
    python scripts/eval_blind_review.py --make-template reports/t1-20261113/m05_ratings_template.csv
    python scripts/eval_blind_review.py --ratings <填好的csv> [--json <输出路径>]

口径：κ 为未加权 Cohen's κ（类别 1–5 分）；某评者评分零方差时 κ 无定义，输出 null 并给原因。
只有 κ>0.6 才允许在材料中写“一致性良好”。
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from itertools import combinations
from pathlib import Path

DIMENSIONS = ("usefulness", "accuracy", "trust")
RATERS = ("R1", "R2", "R3")
SCORES = (1, 2, 3, 4, 5)


def make_template(path: Path, samples: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["sample_id", "rater", "dimension", "score"])
        for index in range(1, samples + 1):
            for rater in RATERS:
                for dimension in DIMENSIONS:
                    writer.writerow([f"S{index:02d}", rater, dimension, ""])


def load_ratings(path: Path) -> dict[str, dict[str, dict[str, int]]]:
    """返回 dimension -> rater -> sample_id -> score。空行/空格跳过并计数。"""
    ratings: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(dict))
    skipped = 0
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            raw = (row.get("score") or "").strip()
            if not raw:
                skipped += 1
                continue
            score = int(raw)
            if score not in SCORES:
                raise ValueError(f"score 必须为 1-5：{row}")
            dimension = row["dimension"].strip()
            if dimension not in DIMENSIONS:
                raise ValueError(f"未知维度：{row}")
            ratings[dimension][row["rater"].strip()][row["sample_id"].strip()] = score
    if skipped:
        print(f"note: 跳过空白评分 {skipped} 格（未评完的维度按实际 n 汇总）")
    return ratings


def cohens_kappa(left: dict[str, int], right: dict[str, int]) -> dict:
    """两评者在共有样本上的未加权 κ。零方差时返回 value=None。"""
    common = sorted(set(left) & set(right))
    n = len(common)
    if n == 0:
        return {"n": 0, "value": None, "note": "无共有样本"}
    observed = sum(1 for s in common if left[s] == right[s]) / n
    expected = 0.0
    for category in SCORES:
        p_left = sum(1 for s in common if left[s] == category) / n
        p_right = sum(1 for s in common if right[s] == category) / n
        expected += p_left * p_right
    if expected == 1.0:
        return {"n": n, "observed": observed, "value": None,
                "note": "至少一方评分零方差（如全部同分），κ 无定义"}
    return {"n": n, "observed": round(observed, 4),
            "value": round((observed - expected) / (1 - expected), 4)}


def summarize(ratings: dict) -> dict:
    report: dict = {"dimensions": {}, "interpretation": "κ>0.6 才可写“一致性良好”；n 为实际评分数"}
    for dimension in DIMENSIONS:
        by_rater = ratings.get(dimension, {})
        scores = [s for samples in by_rater.values() for s in samples.values()]
        entry = {
            "n_ratings": len(scores),
            "n_samples": len({s for samples in by_rater.values() for s in samples}),
            "mean": round(sum(scores) / len(scores), 4) if scores else None,
            "pairwise_kappa": {},
        }
        kappas = []
        for left, right in combinations(sorted(by_rater), 2):
            result = cohens_kappa(by_rater[left], by_rater[right])
            entry["pairwise_kappa"][f"{left}|{right}"] = result
            if result["value"] is not None:
                kappas.append(result["value"])
        entry["mean_pairwise_kappa"] = round(sum(kappas) / len(kappas), 4) if kappas else None
        report["dimensions"][dimension] = entry
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ratings", type=Path, help="填好的长表 CSV")
    parser.add_argument("--make-template", type=Path, help="生成空白评分表")
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--json", type=Path, help="可选：把汇总 JSON 写盘")
    args = parser.parse_args()

    if args.make_template:
        make_template(args.make_template, args.samples)
        print(f"template: {args.make_template}（{args.samples} 样本 × {len(RATERS)} 评者 × {len(DIMENSIONS)} 维度，score 留空待真人填写）")
    if args.ratings:
        report = summarize(load_ratings(args.ratings))
        text = json.dumps(report, ensure_ascii=False, indent=2)
        print(text)
        if args.json:
            args.json.write_text(text, encoding="utf-8")
    if not args.ratings and not args.make_template:
        parser.error("需要 --ratings 或 --make-template")


if __name__ == "__main__":
    main()

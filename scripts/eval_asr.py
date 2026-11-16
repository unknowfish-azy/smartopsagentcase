"""
评测 ASR DTW 命令词基线（dev + holdout 双集合，M02 红线口径）。

红线：只报 dev 属于"选择性呈现"——本脚本强制同时输出两个集合；
holdout 若从未参与训练，其准确率才代表真实泛化。
产物：reports/t-asr-<日期>/eval_summary.json
"""

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from agent.asr import DtwCommandRecognizer, extract_features, load_wav_mono  # noqa: E402

DATASET_DIR = REPO / "SmartOps-Dataset" / "asr"


def evaluate_split(recognizer, split):
    rows = []
    for line in (DATASET_DIR / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row["split"] == split:
                rows.append(row)
    correct = 0
    distances = []
    per_label = {}
    started = time.time()
    for row in rows:
        features = extract_features(load_wav_mono(DATASET_DIR / row["path"]))
        hit = recognizer.recognize(features)
        predicted = hit["label"] if hit else ""
        ok = predicted == row["label"]
        correct += ok
        if hit:
            distances.append(hit["distance"])
        stats = per_label.setdefault(row["label"], {"n": 0, "correct": 0})
        stats["n"] += 1
        stats["correct"] += ok
    elapsed = time.time() - started
    return {
        "split": split,
        "n": len(rows),
        "correct": correct,
        "accuracy": round(correct / len(rows), 4) if rows else 0.0,
        "avg_distance": round(sum(distances) / len(distances), 4) if distances else None,
        "eval_seconds": round(elapsed, 1),
        "per_label": per_label,
    }


def main():
    parser = argparse.ArgumentParser(description="评测 DTW 命令词基线（dev+holdout 双集合）")
    parser.add_argument("--templates", default=str(REPO / "agent" / "asr" / "templates.json"))
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    recognizer = DtwCommandRecognizer.load(args.templates)
    modes = sorted(
        {json.loads(line).get("mode", "unknown") for line in (DATASET_DIR / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()}
    )
    results = [evaluate_split(recognizer, "dev"), evaluate_split(recognizer, "holdout")]
    summary = {
        "date": str(date.today()),
        "model": recognizer.MODEL_VERSION,
        "templates_path": args.templates,
        "dataset_mode": modes[0] if len(modes) == 1 else modes,
        "note": (
            "dev 参与训练（中位模板），holdout 独立。"
            "若数据集为 --synthetic 自检模式，指标仅代表管线正确性，不代表真实语音。"
        ),
        "results": results,
    }
    out_dir = Path(args.output_dir) if args.output_dir else REPO / "reports" / f"t-asr-{date.today()}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "eval_summary.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== ASR DTW 命令词基线评测（双集合）===")
    for result in results:
        print(
            f"[{result['split']}] n={result['n']} 正确={result['correct']} "
            f"准确率={result['accuracy']:.2%} 平均距离={result['avg_distance']}"
        )
    print(f"明细: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

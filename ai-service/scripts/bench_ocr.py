"""视觉 OCR 评测 runner（缺口清单第六项「OCR 补齐」）。

用途：用真实截图 / 报表跑本地 RapidOCR，落盘块数、置信度与（有真值时的）CER。

用法：
    # 单图 + 真值
    py -3.14 ai-service/scripts/bench_ocr.py --image page-01.png --truth page-01.txt
    # 目录批量（真值为同名 .txt）
    py -3.14 ai-service/scripts/bench_ocr.py --dir shots/ --truth-dir truth/

输出：
    reports/ocr-eval-<date>.json

口径：
- 引擎不可用时输出 `available=false` 并如实列出原因，**不伪造识别结果**；
- CER 只在提供了真值时计算；无真值只报块数 / 置信度（不冒充准确率）；
- 归一化只去标点与空白（NFKC + 去 P*/Z* 类别），**不删文字**。
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

AI_SERVICE = Path(__file__).resolve().parents[1]
REPO_ROOT = AI_SERVICE.parent
for path in (str(AI_SERVICE), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.vision import ocr as ocr_mod  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports"


def normalize(text: str) -> str:
    """与 ASR 评测同口径：NFKC + 去标点 + 去所有空白（含换行/制表）。"""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", str(text))
    return "".join(
        ch
        for ch in text
        if not ch.isspace() and not unicodedata.category(ch).startswith("P")
    )


def edit_distance(a: str, b: str) -> int:
    """纯 stdlib Levenshtein（与 eval_asr.py 同口径）。"""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (ca != cb),
                )
            )
        previous = current
    return previous[-1]


def cer(hypothesis: str, truth: str) -> float:
    hyp, ref = normalize(hypothesis), normalize(truth)
    if not ref:
        return 0.0 if not hyp else 1.0
    return round(edit_distance(hyp, ref) / len(ref), 4)


def evaluate_image(image_path: Path, truth: str | None, match_text: str | None = None) -> dict:
    from PIL import Image

    started = datetime.now()
    with Image.open(image_path) as raw:
        image = raw.convert("RGB")
    result = ocr_mod.recognize(image)
    record = {
        "path": str(image_path),
        "status": result.status,
        "engine": result.engine,
        "text": result.text,
        "blocks": len(result.blocks),
        "confidence": result.confidence,
        "elapsed_ms": result.elapsed_ms,
        "warnings": result.warnings,
    }
    if truth is not None:
        record["truth"] = truth
        record["cer"] = cer(result.text, truth)
        record["exact_match"] = normalize(result.text) == normalize(truth)
    if match_text is not None and result.blocks:
        haystack = normalize(match_text)
        hits = sum(1 for b in result.blocks if normalize(b.text) and normalize(b.text) in haystack)
        record["substring_hits"] = hits
        record["substring_total"] = len(result.blocks)
        record["substring_hit_rate"] = round(hits / len(result.blocks), 4)
    record["evaluated_at"] = started.isoformat(timespec="seconds")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="视觉 OCR 评测")
    parser.add_argument("--image", action="append", default=[], help="待识别图片（可多次）")
    parser.add_argument("--dir", help="图片目录（.png/.jpg/.jpeg/.webp）")
    parser.add_argument("--truth", help="单图真值文本文件（与 --image 单张配对）")
    parser.add_argument("--truth-dir", help="真值目录：每图取同名 .txt")
    parser.add_argument(
        "--match-text",
        help=(
            "参考文本（如文档 HTML 提取的全文）：对每个识别块做归一化子串命中，"
            "报命中率。用于无逐字真值时做可复现的宽松核对，**不是准确率**"
        ),
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--tag", default=None, help="产物标签，默认按日期")
    args = parser.parse_args()

    images = [Path(p) for p in args.image]
    if args.dir:
        root = Path(args.dir)
        images.extend(
            sorted(p for p in root.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"})
        )
    images = sorted({p for p in images if p.exists()})
    if not images:
        print("没有可识别的图片：请用 --image 或 --dir 指定", file=sys.stderr)
        return 2

    info = ocr_mod.get_ocr_info()
    if not info["available"]:
        print(f"OCR 引擎不可用：{info['reason']}", file=sys.stderr)

    match_text = Path(args.match_text).read_text(encoding="utf-8") if args.match_text else None

    records = []
    for image in images:
        truth_path = None
        if args.truth_dir:
            candidate = Path(args.truth_dir) / (image.stem + ".txt")
            truth_path = candidate if candidate.exists() else None
        elif args.truth and len(images) == 1:
            truth_path = Path(args.truth)
        truth = truth_path.read_text(encoding="utf-8") if truth_path else None
        try:
            record = evaluate_image(image, truth, match_text)
        except Exception as exc:  # noqa: BLE001 - 单图失败不拖垮整轮，如实留痕
            record = {"path": str(image), "status": "FAILED", "warnings": [f"{type(exc).__name__}: {exc}"]}
        records.append(record)

    scored = [r for r in records if r.get("cer") is not None]
    matched = [r for r in records if r.get("substring_total")]
    summary = {
        "n_images": len(records),
        "n_scored": len(scored),
        "status_counts": {
            status: sum(1 for r in records if r["status"] == status)
            for status in {r["status"] for r in records}
        },
        "blocks_total": sum(r.get("blocks", 0) for r in records),
        "mean_confidence": _mean([r.get("confidence") for r in records]),
        "mean_cer": _mean([r["cer"] for r in scored]) if scored else None,
        "exact_rate": (
            round(sum(1 for r in scored if r["exact_match"]) / len(scored), 4) if scored else None
        ),
        "substring_hit_rate": (
            round(sum(r["substring_hits"] for r in matched) / sum(r["substring_total"] for r in matched), 4)
            if matched
            else None
        ),
        "substring_blocks": sum(r.get("substring_total", 0) for r in records),
    }

    tag = args.tag or datetime.now().strftime("%Y-%m-%d")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"ocr-eval-{tag}.json"
    payload = {
        "experiment_id": f"EXP-OCR-{tag}",
        "engine": info["kind"],
        "available": bool(info["available"]),
        "engine_reason": info["reason"],
        "summary": summary,
        "images": records,
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"产物：{output}")
    return 0


def _mean(values):
    items = [v for v in values if v is not None]
    return round(sum(items) / len(items), 4) if items else None


if __name__ == "__main__":
    raise SystemExit(main())

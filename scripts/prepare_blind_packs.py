"""M05 P0：把 answers.jsonl 加工成三位评者的盲评包。

产物（均在 --out-dir 下）：
  packs/pack_R1.md / pack_R2.md / pack_R3.md   评者只拿到这个：S 编号 + 问题 + 回答，顺序各自随机
  packs/ratings_R1.csv / _R2 / _R3             与包内顺序一致的空白评分表（sample_id,rater,dimension,score）
  answers_mapping_private.csv                  私有映射（模型/时间/备注），**不发给评者**
  packs_manifest.json                          随机种子、脱敏替换计数、来源 sha256，供复现与归档

脱敏规则命中即计数；生成后若仍检出敏感词则报错退出，不允许发出。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
from pathlib import Path

REPLACEMENTS = [
    (re.compile(r"(?i)smartops\s*agent"), "该平台"),
    (re.compile(r"(?i)smartops"), "该平台"),
    ("智维", "该平台"),
    (re.compile(r"(?i)qwen\d*[:\-]?[0-9.]*b?"), "本地模型"),
    (re.compile(r"(?i)ollama"), "本地推理服务"),
    (re.compile(r"(?i)bge-[a-z0-9\-]+"), "向量模型"),
]
FORBIDDEN = ["smartops", "智维", "qwen", "ollama", "bge", "本系统", "我们的", "模拟回答", "开发阶段"]
DIMENSIONS = ("usefulness", "accuracy", "trust")


def sanitize(text: str, counter: dict[str, int]) -> str:
    for pattern, replacement in REPLACEMENTS:
        text, n = pattern.subn(replacement, text) if hasattr(pattern, "subn") else (text.replace(pattern, replacement), text.count(pattern))
        if n:
            counter[str(pattern)] = counter.get(str(pattern), 0) + n
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20261113, help="随机种子基准，R1/R2/R3 分别 +1/+2/+3")
    args = parser.parse_args()

    raw = args.answers.read_bytes()
    records = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    if len(records) != 30:
        raise SystemExit(f"样本数应为 30，实际 {len(records)}")
    counter: dict[str, int] = {}
    for rec in records:
        rec["clean_answer"] = sanitize(rec["answer"], counter)
        rec["clean_question"] = sanitize(rec["question"], counter)

    packs = args.out_dir / "packs"
    packs.mkdir(parents=True, exist_ok=True)
    for offset, rater in enumerate(("R1", "R2", "R3"), start=1):
        order = records[:]
        random.Random(args.seed + offset).shuffle(order)
        lines = [f"# 盲评材料（{rater}）", "", "共 30 条，每条含问题与回答。请按评分细则对有用性/准确性/可信度分别打 1-5 分，", "评分填入同目录 ratings 表，顺序与本文件一致。无法判断的格子留空。", ""]
        with (packs / f"ratings_{rater}.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["sample_id", "rater", "dimension", "score"])
            for rec in order:
                lines += [f"## {rec['sample_id']}", "", f"**问题**：{rec['clean_question']}", "", "**回答**：", "", rec["clean_answer"], "", "---", ""]
                for dim in DIMENSIONS:
                    writer.writerow([rec["sample_id"], rater, dim, ""])
        (packs / f"pack_{rater}.md").write_text("\n".join(lines), encoding="utf-8")

    for pack in packs.glob("pack_R*.md"):
        text = pack.read_text(encoding="utf-8").lower()
        leaked = [t for t in FORBIDDEN if t.lower() in text]
        if leaked:
            raise SystemExit(f"{pack.name} 仍含敏感词 {leaked}，禁止发出")

    with (args.out_dir / "answers_mapping_private.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["sample_id", "question", "answer_chars", "llm_model", "collected_at", "note"])
        for rec in records:
            writer.writerow([rec["sample_id"], rec["question"], rec["answer_chars"], rec["llm_model"], rec["collected_at"], rec.get("note", "")])

    manifest = {
        "source": str(args.answers),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "n_samples": len(records),
        "seeds": {r: args.seed + i for i, r in enumerate(("R1", "R2", "R3"), start=1)},
        "sanitization_replacements": counter,
        "forbidden_scan": "pass",
        "private_file": "answers_mapping_private.csv（不随评分包发出）",
    }
    (args.out_dir / "packs_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

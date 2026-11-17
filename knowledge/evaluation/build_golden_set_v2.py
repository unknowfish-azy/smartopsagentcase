"""D2 评测集 v2：把检索用例从 114 条扩到 300+ 条（自动生成，待人工复核）。

与 v1（build_golden_set.py → golden_set.json）的差异：

- 每篇文档出 3 类问法：``verbatim``（标题原词）、``paraphrase``（同义改写）、
  ``scenario``（值班口吻的排障场景），语义跨度递增；
- 许可已判定 REJECTED 的语料（``RH教材/``，红帽官方教材）**不进入**评测集，
  其余来源逐条标注 ``license_status``，便于事后只取 approved 子集作正式口径；
- 每条 case 带稳定 ``case_id``、``provenance``、``review_status``，
  并额外产出 manifest 与 30% 分层复核表；
- 生成过程纯规则、确定性：同样语料重跑得到逐字节相同的 golden_set_v2.json。

注意：自动生成只能衡量"改写鲁棒性"，不能替代人工标注。
``review_status`` 在人工复核前一律为 ``unreviewed``，正式对外结论必须等复核完成。

用法：

    python -m knowledge.evaluation.build_golden_set_v2
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from knowledge.evaluation.build_golden_set import (
    _GENERIC_TITLES,
    _clean_title,
    _first_heading,
    _first_section,
    _paraphrase,
    REFERENCE_ROOT,
)

EVAL_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = EVAL_DIR / "golden_set_v2.json"
DEFAULT_MANIFEST = EVAL_DIR / "golden_set_v2.manifest.json"
DEFAULT_REVIEW = EVAL_DIR / "golden_set_v2.review.csv"
SCHEMA = "smartops.retrieval_eval.v2"

# 许可 REJECTED 的目录：红帽官方教材写有 "Internal use only - Not For Sale"，
# 见 docs/development/P0-DATA-02-artifact_registry.csv 的 ART-001/002/003。
EXCLUDED_DIRS = {
    "RH教材": "REJECTED: 红帽官方培训教材，禁止入库/入评测集（ART-001/002/003）",
}

# 目录 → 登记状态（引用 P0-DATA-02 registry 的登记号）。
LICENSE_BY_DIR = {
    "SmartOpsAgent-项目知识": "approved",
    "AI-Infra": "pending: 未登记（语雀训练营蒸馏）",
    "AI Infra训练营二期_分课": "pending: 未登记",
    "Docker运维课": "pending: 未登记",
    "Prometheus监控课_分节md": "pending: ART-021",
    "云原生公开课_分章md": "pending: ART-004",
    "(root)": "pending: ART-005",
}
DEFAULT_LICENSE = "pending: 未登记"

_SCENARIO_TEMPLATES = (
    "线上告警涉及{topic}，值班时先核对哪些证据再动手？",
    "交接班被问到{topic}，需要准备怎样的说明？",
    "{topic}出现异常，如何分步定位并验证恢复？",
    "新人问{topic}具体怎么做，按什么顺序讲？",
)

_PARAPHRASE_TEMPLATES = (
    "{topic} 一般怎么处理？",
    "线上遇到 {topic} 相关问题时，排查顺序是什么？",
    "同事问 {topic} 这块该怎么入手，怎么回答？",
    "{topic} 出了问题，第一步先看什么？",
)

_VERBATIM_TEMPLATES = (
    "{topic}是什么？",
    "{topic}怎么操作？",
    "{topic}有哪些关键点？",
)


def _shorten(text: str, limit: int = 26) -> str:
    """长标题先截断，避免生成"问题是半句话"的查询。"""
    return text if len(text) <= limit else text[:limit].rstrip("，,。、 ")


_LESSON_PREFIX = re.compile(r"^第\s*[0-9０-９一二三四五六七八九十百]+\s*[课讲节章篇]\s*")
_HEADING_TAIL = re.compile(r"[\s\-—_]*(概述|概览|简介|介绍|总览|导论|说明|总结|小结)$")


def _strip_lesson_noise(text: str) -> str:
    """去掉"第1课 ""xxx概述"这类标题噪声，避免问句里出现课程编号。"""
    return _HEADING_TAIL.sub("", _LESSON_PREFIX.sub("", text)).strip() or text


def _corpus_dir(path: Path, root: Path) -> str:
    relative = path.relative_to(root)
    return relative.parts[0] if len(relative.parts) > 1 else "(root)"


def build_cases(root: Path = REFERENCE_ROOT) -> tuple[list[dict], dict]:
    """扫描语料生成 case 列表与统计信息（不含时间戳，便于校验确定性）。"""
    cases: list[dict] = []
    seen: set[str] = set()
    documents = 0
    excluded_docs = 0
    license_counts: dict[str, int] = defaultdict(int)

    for path in sorted(root.rglob("*.md")):
        corpus_dir = _corpus_dir(path, root)
        if corpus_dir in EXCLUDED_DIRS:
            excluded_docs += 1
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        title = _first_heading(text) or _clean_title(path.stem)
        title = _strip_lesson_noise(title)
        if len(title) < 4 or title in _GENERIC_TITLES:
            continue

        license_status = LICENSE_BY_DIR.get(corpus_dir, DEFAULT_LICENSE)
        # 与 evaluation.runner.seed_corpus 保持完全一致的 source 拼接方式。
        source = f"reference/{path.relative_to(root)}"
        topic = _shorten(_strip_lesson_noise(_first_section(text) or title))
        title = _shorten(title)
        offset = documents % len(_PARAPHRASE_TEMPLATES)

        candidates = [
            (
                _VERBATIM_TEMPLATES[documents % len(_VERBATIM_TEMPLATES)].format(topic=title),
                "verbatim",
                "rule:title",
            ),
            (
                _PARAPHRASE_TEMPLATES[offset].format(topic=_paraphrase(topic)),
                "paraphrase",
                "rule:synonym",
            ),
            (
                _SCENARIO_TEMPLATES[offset].format(topic=topic),
                "scenario",
                "rule:scenario",
            ),
        ]

        documents += 1
        for question, style, provenance in candidates:
            question = " ".join(question.split())
            if not question or question in seen:
                continue
            seen.add(question)
            license_counts[license_status] += 1
            cases.append(
                {
                    "case_id": f"case-ret-{len(cases) + 1:04d}",
                    "question": question,
                    "expected_sources": [source],
                    "style": style,
                    "version": "reference",
                    "corpus_dir": corpus_dir,
                    "license_status": license_status,
                    "provenance": provenance,
                    "review_status": "unreviewed",
                }
            )

    stats = {
        "documents": documents,
        "excluded_documents": excluded_docs,
        "license_counts": dict(sorted(license_counts.items())),
    }
    return cases, stats


def sample_review(cases: list[dict], ratio: float = 0.3) -> list[dict]:
    """按 style 分层抽样，用问题哈希排序保证可复现。"""
    buckets: dict[str, list[dict]] = defaultdict(list)
    for case in cases:
        buckets[case["style"]].append(case)

    sample: list[dict] = []
    for style in sorted(buckets):
        ordered = sorted(
            buckets[style],
            key=lambda case: hashlib.sha256(case["question"].encode("utf-8")).hexdigest(),
        )
        take = max(1, round(len(ordered) * ratio))
        sample.extend(ordered[:take])
    return sorted(sample, key=lambda case: case["case_id"])


def write_review_sheet(cases: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "case_id",
                "style",
                "corpus_dir",
                "license_status",
                "question",
                "expected_source",
                "relevance_a_1to5",
                "relevance_b_1to5",
                "adjudication",
            ]
        )
        for case in cases:
            writer.writerow(
                [
                    case["case_id"],
                    case["style"],
                    case["corpus_dir"],
                    case["license_status"],
                    case["question"],
                    case["expected_sources"][0],
                    "",
                    "",
                    "",
                ]
            )


def build_manifest(
    cases: list[dict],
    stats: dict,
    *,
    dataset_path: Path,
    review_size: int,
    ratio: float,
) -> dict:
    by_style: dict[str, int] = defaultdict(int)
    by_dir: dict[str, int] = defaultdict(int)
    approved = 0
    for case in cases:
        by_style[case["style"]] += 1
        by_dir[case["corpus_dir"]] += 1
        if case["license_status"] == "approved":
            approved += 1

    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_root": "knowledge/reference/ops-knowledge-rag",
        "case_count": len(cases),
        "effective_independent_units": stats["documents"],
        "documents": stats["documents"],
        "by_style": dict(sorted(by_style.items())),
        "by_corpus_dir": dict(sorted(by_dir.items())),
        "license_distribution": stats["license_counts"],
        "approved_subset_cases": approved,
        "excluded_dirs": EXCLUDED_DIRS,
        "excluded_documents": stats["excluded_documents"],
        "review": {
            "ratio": ratio,
            "sample_size": review_size,
            "status": "pending_human",
        },
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "notes": [
            "自动生成仅衡量改写鲁棒性，不替代人工标注",
            "正式对外指标只能基于 license_status=approved 子集 + 人工复核通过的 case",
            "按文档数计有效独立样本，多问法之间存在相关性",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REFERENCE_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--ratio", type=float, default=0.3, help="人工复核抽样比例")
    args = parser.parse_args(argv)

    cases, stats = build_cases(args.root)
    args.output.write_text(
        json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    review = sample_review(cases, args.ratio)
    write_review_sheet(review, args.review)

    manifest = build_manifest(
        cases, stats, dataset_path=args.output, review_size=len(review), ratio=args.ratio
    )
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"用例 {len(cases)} 条（文档 {stats['documents']} 篇，已排除 {stats['excluded_documents']} 篇）→ {args.output}")
    print(f"问法分布：{manifest['by_style']}")
    print(f"许可分布：{manifest['license_distribution']}；approved 子集 {manifest['approved_subset_cases']} 条")
    print(f"人工复核抽样 {len(review)} 条（{args.ratio:.0%}）→ {args.review}")
    if len(cases) < 300:
        print(f"警告：用例数 {len(cases)} 未达到 D2 目标 300")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

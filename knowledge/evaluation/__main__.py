"""检索评测命令行。

用法：

    python -m knowledge.evaluation                      # hash + bge 对比
    python -m knowledge.evaluation --backends hash       # 只跑哈希基线
    python -m knowledge.evaluation --top-k 10 --json out.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from knowledge.config import KnowledgeConfig
from knowledge.embedding.factory import create_embedding
from knowledge.evaluation.dataset import load_dataset
from knowledge.evaluation.runner import evaluate_service, seed_corpus
from knowledge.service import KnowledgeService

EVAL_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET = EVAL_DIR / "golden_set.json"
REFERENCE_ROOT = EVAL_DIR.parent / "reference" / "ops-knowledge-rag"


def _run_backend(backend: str, cases, top_k: int) -> dict:
    # 复用服务端同一份向量缓存，重复评测不必重新编码语料。
    embedding = create_embedding(
        backend,
        cache_path=KnowledgeConfig().vector_cache_path,
    )
    # 回退时能看出真实用了哪种后端。
    actual = type(embedding).__name__

    service = KnowledgeService(
        KnowledgeConfig(chunk_size=800, chunk_overlap=120),
        embedding=embedding,
    )
    seeded = seed_corpus(service, REFERENCE_ROOT)

    summary = evaluate_service(service, cases, top_k=top_k)
    summary["backend"] = backend
    summary["backend_actual"] = actual
    summary["documents"] = seeded
    summary["chunks"] = service.chunk_count
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="知识库检索评测")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--backends", default="hash,bge")
    parser.add_argument("--json", default="")
    args = parser.parse_args()

    cases = load_dataset(args.dataset)
    if not cases:
        raise SystemExit("评测集为空，请先运行 python -m knowledge.evaluation.build_golden_set")

    results = [
        _run_backend(backend.strip(), cases, args.top_k)
        for backend in args.backends.split(",")
        if backend.strip()
    ]

    header = f"{'backend':<10}{'actual':<20}{'cases':>6}{'hit@k':>8}{'recall':>8}{'mrr':>8}{'ndcg':>8}{'p50ms':>8}"
    print(header)
    print("-" * len(header))
    for row in results:
        print(
            f"{row['backend']:<10}"
            f"{row['backend_actual']:<20}"
            f"{row['cases']:>6}"
            f"{row['hit@k']:>8.3f}"
            f"{row['recall@k']:>8.3f}"
            f"{row['mrr']:>8.3f}"
            f"{row['ndcg@k']:>8.3f}"
            f"{row['latency_ms_p50']:>8.1f}"
        )

    print("\n分组（verbatim = 保留标题原词，paraphrase = 同义改写）：")
    for row in results:
        for style, info in row["by_style"].items():
            print(
                f"  {row['backend']:<8} {style:<12}"
                f"cases={info['cases']:<4}"
                f"hit={info['hit@k']:.3f} "
                f"recall={info['recall@k']:.3f} "
                f"mrr={info['mrr']:.3f} "
                f"ndcg={info['ndcg@k']:.3f}"
            )

    if args.json:
        Path(args.json).write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n明细已写入 {args.json}")


if __name__ == "__main__":
    main()

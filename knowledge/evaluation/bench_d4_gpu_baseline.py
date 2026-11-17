"""D4 GPU 基线：对比 BGE 在 CPU 与 CUDA 上的延迟与精度。

设计约束：

- RTX 4060 8GB，bge-small-zh-v1.5 ~100MB，显存足够；
- 同一语料、同一 backend、同一 batch_size 下比 wall-clock，避免缓存命中影响结果；
- 用 golden_set_v2 的问题做真实载荷，benchmark 完再用标准评测确认向量不变（一致性）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# 先锁离线模式，避免 transformers/hf_hub 在加载时 HEAD 请求 HF。
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from knowledge.embedding.factory import create_embedding  # noqa: E402


def collect_texts(root: Path | None = None, max_docs: int = 500) -> list[str]:
    root = root or (PROJECT_ROOT / "knowledge" / "reference" / "ops-knowledge-rag")
    texts: list[str] = []
    for path in sorted(root.rglob("*.md"))[:max_docs]:
        content = path.read_text(encoding="utf-8", errors="ignore").strip()
        if content:
            texts.append(content[:512])
    return texts


def run_benchmark(
    backend: str,
    device: str | None,
    texts: list[str],
    *,
    batch_size: int = 16,
    warmup_batches: int = 2,
    iterations: int = 3,
) -> dict:
    """在指定 device 上跑 warmup + iterations，取中位数。"""
    model = create_embedding(backend=backend, device=device)
    status = model.backend_status
    print(f"loading done: actual={status.backend_actual} device={status.device} dim={status.dimension}")

    # GPU 同步点：torch.cuda.synchronize 让计时准确
    try:
        import torch
        if device and device.startswith("cuda"):
            sync = torch.cuda.synchronize
        else:
            sync = lambda: None
    except ImportError:
        sync = lambda: None

    batches = [texts[i : i + batch_size] for i in range(0, len(texts), batch_size)]

    # warmup
    for i, batch in enumerate(batches[:warmup_batches]):
        model.encode(batch, is_query=False)
        sync()

    per_call_ms: list[float] = []
    vectors: list[list[float]] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        for batch in batches:
            vectors.extend(model.encode(batch, is_query=False))
        sync()
        elapsed = (time.perf_counter() - t0) * 1000
        per_call_ms.append(elapsed / len(batches))

    arr = np.array(per_call_ms)
    return {
        "backend": backend,
        "device": status.device,
        "backend_actual": status.backend_actual,
        "total_texts": len(texts),
        "batch_size": batch_size,
        "batches": len(batches),
        "iterations": iterations,
        "latency_p50_ms": float(np.median(arr)),
        "latency_p90_ms": float(np.quantile(arr, 0.90)),
        "latency_min_ms": float(arr.min()),
        "latency_max_ms": float(arr.max()),
        "throughput_texts_per_sec": round(len(batches) * batch_size / (np.median(arr) / 1000), 1),
        "sample_vector": vectors[0][:8],
    }


def verify_consistency(cpu_vecs: list[list[float]], gpu_vecs: list[list[float]], texts: list[str]) -> dict:
    """同一文本 CPU 与 GPU 的向量应完全一致（同一 torch 版本下）。"""
    if len(cpu_vecs) != len(gpu_vecs):
        return {"ok": False, "reason": "向量长度不一致", "cpu": len(cpu_vecs), "gpu": len(gpu_vecs)}

    diffs = []
    for cpu, gpu in zip(cpu_vecs, gpu_vecs):
        cpu_arr = np.array(cpu)
        gpu_arr = np.array(gpu)
        diffs.append(float(np.abs(cpu_arr - gpu_arr).max()))

    return {
        "ok": max(diffs) < 1e-5,
        "max_abs_diff": float(max(diffs)),
        "mean_abs_diff": float(np.mean(diffs)),
        "samples": len(diffs),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=None)
    parser.add_argument("--max-docs", type=int, default=300)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    texts = collect_texts(args.corpus, args.max_docs)
    print(f"benchmark texts={len(texts)} batch={args.batch_size}")

    cpu = run_benchmark("bge", "cpu", texts, batch_size=args.batch_size)
    gpu = run_benchmark("bge", "cuda", texts, batch_size=args.batch_size)

    # 做一次确定性一致性验证：同一批文本两次 encode（CPU vs GPU）应逐元素相等
    cpu_model = create_embedding("bge", device="cpu")
    gpu_model = create_embedding("bge", device="cuda")
    cpu_vecs = cpu_model.encode(texts[:50])
    gpu_vecs = gpu_model.encode(texts[:50])
    consistency = verify_consistency(cpu_vecs, gpu_vecs, texts[:50])

    speedup = cpu["latency_p50_ms"] / gpu["latency_p50_ms"] if gpu["latency_p50_ms"] else 0

    report = {
        "consistency": consistency,
        "speedup_p50x": round(speedup, 2),
        "cpu": cpu,
        "gpu": gpu,
        "notes": [
            f"CPU latency p50={cpu['latency_p50_ms']:.1f}ms/batch, GPU p50={gpu['latency_p50_ms']:.1f}ms/batch",
            f"吞吐提升 {speedup:.1f}x",
            "向量一致性 max_abs_diff 理想为 0（同 torch 版本、同 seed）",
        ],
    }

    print("\n=== CPU vs GPU (bge, batch=%d) ===" % args.batch_size)
    print(f"         {'CPU':>12}{'GPU':>12}{'Δ':>10}")
    print(f"p50 ms   {cpu['latency_p50_ms']:>12.1f}{gpu['latency_p50_ms']:>12.1f}{speedup:>10.1f}x")
    print(f"p90 ms   {cpu['latency_p90_ms']:>12.1f}{gpu['latency_p90_ms']:>12.1f}")
    print(f"thr/s    {cpu['throughput_texts_per_sec']:>12}{gpu['throughput_texts_per_sec']:>12}")
    print(f"consist  {'OK' if consistency['ok'] else 'FAIL':>12}{consistency['max_abs_diff']:>12.2e}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\n明细 → {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

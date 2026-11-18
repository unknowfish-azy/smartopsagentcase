"""P2 阶段 2：TraceFormer 调用链异常感知训练脚本。

任务：span 序列 → 每 span 异常分（span 级二分类）。训练可复用权重供推理服务加载
（ai-service/models/traceformer.pt），把 heuristic 升级为真模型。

数据：--mock 合成调用链（正常 + 注入慢/错 span），span 级弱标注（错误/慢即为正例）。
标签即启发式规则，因此 TraceFormer 学习的是"可泛化的耗时/状态/深度联合模式"，
评测与 heuristic 基线对比 span 级 F1 / PR-AUC。

用法：
    python scripts/train_trace.py --mock
    python scripts/train_trace.py --mock --epochs 40 --num-traces 300
    python scripts/train_trace.py --mock --model-dir ../models   # 保存 traceformer.pt
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.training.trace_model import (  # noqa: E402
    NUM_FEATURES,
    TraceFormer,
    available,
    build_feature_matrix,
    heuristic_span_scores,
)

MODE = available()

SERVICES = ["gateway", "order", "user", "payment", "mysql", "redis", "cache", "mq"]


# ---------------------------------------------------------------------------
# 合成调用链
# ---------------------------------------------------------------------------

def generate_traces(num_traces: int = 200, seed: int = 42) -> list[dict]:
    """生成正常 + 异常调用链。异常：随机注入慢 span（duration 飙升）或错误 span（status 500）。"""
    rng = np.random.default_rng(seed)
    traces = []
    for t in range(num_traces):
        depth = int(rng.integers(2, 6))
        services = list(rng.choice(SERVICES, size=depth, replace=False))
        is_anomaly = rng.random() < 0.5  # 一半异常
        spans = []
        for i in range(depth):
            duration = float(rng.uniform(10, 120))     # 正常耗时
            status = 200
            if is_anomaly and i == depth - 1:          # 叶子节点注入异常（最像真实根因）
                if rng.random() < 0.5:
                    duration = float(rng.uniform(1000, 5000))  # 慢
                else:
                    status = 500                                # 错误
            spans.append({
                "span_id": f"t{t}_s{i}",
                "parent_id": f"t{t}_s{i-1}" if i > 0 else None,
                "service": services[i],
                "operation": "op",
                "duration_ms": duration,
                "status_code": status,
                "is_error": status >= 500,
            })
        traces.append({"spans": spans})
    return traces


def _labels(spans: list[dict], slow_threshold_ms: float = 1000.0) -> np.ndarray:
    """span 级弱标注：错误或慢 → 1。"""
    return np.asarray(
        [1.0 if (s["is_error"] or s["duration_ms"] >= slow_threshold_ms) else 0.0 for s in spans],
        dtype=np.float32,
    )


# ---------------------------------------------------------------------------
# 训练 + 评测
# ---------------------------------------------------------------------------

def train(model, traces, epochs: int, lr: float) -> list[float]:
    import torch

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    pos_weight = torch.tensor(3.0)  # 异常 span 少，加权
    loss_fn = torch.nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    losses = []
    for ep in range(epochs):
        model.train()
        ep_loss = 0.0
        for tr in traces:
            spans = tr["spans"]
            x = torch.as_tensor(build_feature_matrix(spans)).unsqueeze(0)  # [1,T,F]
            y = torch.as_tensor(_labels(spans)).unsqueeze(0)               # [1,T]
            optimizer.zero_grad()
            logits = model(x)                                              # [1,T]
            loss = loss_fn(logits, y)
            loss.backward()
            optimizer.step()
            ep_loss += float(loss.item())
        losses.append(ep_loss / max(len(traces), 1))
        if (ep + 1) % 10 == 0 or ep == 0:
            print(f"  epoch {ep+1}/{epochs}  loss={losses[-1]:.4f}")
    return losses


def evaluate(model, traces) -> dict:
    """span 级 F1 / PR-AUC，模型 vs heuristic。"""
    import torch

    def pr_auc(scores, labels):
        order = np.argsort(-scores)
        l = labels[order]
        tp = np.cumsum(l)
        fp = np.cumsum(1 - l)
        denom = tp + fp
        precision = np.divide(tp, np.maximum(denom, 1e-9))
        recall = tp / max(l.sum(), 1e-9)
        trapz = getattr(np, "trapezoid", None) or np.trapz  # numpy 2.x 改名
        return float(trapz(precision, recall))

    def f1(scores, labels):
        pred = (scores >= 0.5).astype(np.float32)
        tp = float(((pred == 1) & (labels == 1)).sum())
        fp = float(((pred == 1) & (labels == 0)).sum())
        fn = float(((pred == 0) & (labels == 1)).sum())
        p = tp / max(tp + fp, 1e-9)
        r = tp / max(tp + fn, 1e-9)
        return float(2 * p * r / max(p + r, 1e-9))

    m_scores, h_scores, all_labels = [], [], []
    model.eval()
    with torch.no_grad():
        for tr in traces:
            spans = tr["spans"]
            y = _labels(spans)
            m = model.predict_scores(build_feature_matrix(spans))
            h = heuristic_span_scores(spans)
            m_scores.append(m)
            h_scores.append(h)
            all_labels.append(y)

    m_scores = np.concatenate(m_scores)
    h_scores = np.concatenate(h_scores)
    all_labels = np.concatenate(all_labels)
    return {
        "traceformer": {"f1": f1(m_scores, all_labels), "pr_auc": pr_auc(m_scores, all_labels)},
        "heuristic": {"f1": f1(h_scores, all_labels), "pr_auc": pr_auc(h_scores, all_labels)},
        "num_spans": int(all_labels.size),
        "positive_ratio": float(all_labels.mean()),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--num-traces", type=int, default=200)
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--d-model", type=int, default=64)
    parser.add_argument("--max-len", type=int, default=256)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model-dir", type=Path, default=None)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    if MODE == "heuristic":
        print("❌ torch 不可用，无法训练")
        return 1
    if not args.mock:
        print("⚠️  请用 --mock 模式（真实数据待接入）")
        return 1

    import torch
    torch.manual_seed(args.seed)

    traces = generate_traces(args.num_traces, seed=args.seed)
    split = int(len(traces) * 0.8)
    train_set, test_set = traces[:split], traces[split:]
    print(f"mode={MODE}  traces={len(traces)} (train={len(train_set)} test={len(test_set)})")

    model = TraceFormer(d_model=args.d_model, max_len=args.max_len)
    train(model, train_set, args.epochs, args.lr)

    report = evaluate(model, test_set)
    print(f"\n=== 测试集 span 级评测（{report['num_spans']} spans, 正例比 {report['positive_ratio']:.2f}）===")
    print(f"{'metric':<10}{'heuristic':>12}{'traceformer':>14}")
    for metric in ("f1", "pr_auc"):
        h = report["heuristic"][metric]
        m = report["traceformer"][metric]
        print(f"{metric:<10}{h:>12.3f}{m:>14.3f}   Δ{m-h:+.3f}")

    if args.model_dir:
        args.model_dir.mkdir(parents=True, exist_ok=True)
        save_path = args.model_dir / "traceformer.pt"
        torch.save({"model_state": model.state_dict(), "max_len": args.max_len}, save_path)
        print(f"\n模型 → {save_path}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"明细 → {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

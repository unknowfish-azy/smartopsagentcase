"""P2 阶段 3：TGAT 动态拓扑根因训练脚本。

任务：时间切片图序列 → 节点根因分（节点级二分类）。训练可复用权重供推理服务加载
（ai-service/models/tgat.pt），把 heuristic 升级为真模型。

数据：--mock 合成动态拓扑 + 故障传播场景（正常 → 根因异常 → 沿调用链扩散），
根因节点为最早异常的节点（标签=1）。评测 top1/top3/MRR，与 heuristic 基线对比。

用法：
    python scripts/train_tgat.py --mock
    python scripts/train_tgat.py --mock --epochs 60 --num-events 200
    python scripts/train_tgat.py --mock --model-dir ../models   # 保存 tgat.pt
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.training.tgat_model import (  # noqa: E402
    TGATRootCause,
    align_nodes,
    available,
    heuristic_tgat_scores,
    snapshot_edge_index,
    snapshot_features,
)

MODE = available()

SERVICES = ["gateway", "order", "user", "payment", "mysql", "redis", "cache", "mq", "search"]


# ---------------------------------------------------------------------------
# 合成动态拓扑 + 故障传播
# ---------------------------------------------------------------------------

def generate_events(num_events: int = 200, seed: int = 42) -> list[dict]:
    """每个事件：一条调用链 + 随机根因节点，3-4 个时间切片模拟故障从根因向下游扩散。"""
    rng = np.random.default_rng(seed)
    events = []
    for _ in range(num_events):
        chain_len = int(rng.integers(3, 6))
        chain = list(rng.choice(SERVICES, size=chain_len, replace=False))
        root_idx = int(rng.integers(1, chain_len))   # 根因不是入口
        num_snaps = int(rng.integers(3, 5))

        snapshots = []
        for k in range(num_snaps):
            nodes = []
            # 故障从 root_idx 开始，随切片向下游扩散
            for i, svc in enumerate(chain):
                if i < root_idx:
                    infected = k >= num_snaps - 1     # 上游最后被波及
                else:
                    infected = (i - root_idx) <= (k - 1)  # 下游逐步感染
                if i == root_idx:
                    infected = k >= 1                 # 根因从 t1 起异常
                sev = ("P0" if i == root_idx else "P1") if infected else "P3"
                status = "OPEN" if infected else "CLOSED"
                nodes.append({"alert_id": svc, "severity": sev, "status": status})
            edges = [{"alert_a_id": chain[i], "alert_b_id": chain[i + 1]} for i in range(chain_len - 1)]
            snapshots.append({"timestamp": 100.0 * (k + 1), "nodes": nodes, "edges": edges})

        events.append({"snapshots": snapshots, "root_id": chain[root_idx]})
    return events


def _prepare(event: dict):
    """构造对齐后的切片张量输入 + 节点标签。"""
    snaps = event["snapshots"]
    node_order = align_nodes(snaps)
    feats, masks, eis = [], [], []
    for s in snaps:
        x, m = snapshot_features(s, node_order)
        feats.append(x)
        masks.append(m)
        eis.append(snapshot_edge_index(s, node_order))
    labels = np.asarray([1.0 if nid == event["root_id"] else 0.0 for nid in node_order], dtype=np.float32)
    return feats, eis, masks, labels


def _ranking(scores: np.ndarray, labels: np.ndarray) -> dict:
    if labels.sum() == 0:
        return {"top1": 0.0, "top3": 0.0, "mrr": 0.0}
    order = np.argsort(-scores)
    ranks = [i + 1 for i in range(len(scores)) if labels[order[i]] == 1]
    return {
        "top1": 1.0 if any(r == 1 for r in ranks) else 0.0,
        "top3": 1.0 if any(r <= 3 for r in ranks) else 0.0,
        "mrr": float(np.mean([1.0 / r for r in ranks])),
    }


def train(model, events, epochs: int, lr: float) -> None:
    import torch

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    prepared = [_prepare(e) for e in events]
    for ep in range(epochs):
        model.train()
        ep_loss = 0.0
        for feats, eis, masks, labels in prepared:
            snaps = [
                (torch.as_tensor(feats[k]), torch.as_tensor(eis[k], dtype=torch.long), torch.as_tensor(masks[k]))
                for k in range(len(feats))
            ]
            y = torch.as_tensor(labels)
            optimizer.zero_grad()
            scores = model(snaps)                       # [N]（已 sigmoid）
            loss = torch.nn.BCELoss()(scores, y)
            loss.backward()
            optimizer.step()
            ep_loss += float(loss.item())
        if (ep + 1) % 20 == 0 or ep == 0:
            print(f"  epoch {ep+1}/{epochs}  loss={ep_loss/len(prepared):.4f}")


def evaluate(model, events) -> dict:
    deep = {"top1": [], "top3": [], "mrr": []}
    heur = {"top1": [], "top3": [], "mrr": []}
    model.eval()
    for e in events:
        feats, eis, masks, labels = _prepare(e)
        snaps = [(feats[k], eis[k], masks[k]) for k in range(len(feats))]
        d = model.predict(snaps)
        h = heuristic_tgat_scores(feats, masks)
        for key in deep:
            deep[key].append(_ranking(d, labels)[key])
            heur[key].append(_ranking(h, labels)[key])
    return {
        "tgat": {k: float(np.mean(v)) for k, v in deep.items()},
        "heuristic": {k: float(np.mean(v)) for k, v in heur.items()},
        "num_events": len(events),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--num-events", type=int, default=200)
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--d-model", type=int, default=32)
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

    events = generate_events(args.num_events, seed=args.seed)
    split = int(len(events) * 0.8)
    train_set, test_set = events[:split], events[split:]
    print(f"mode={MODE}  events={len(events)} (train={len(train_set)} test={len(test_set)})")

    model = TGATRootCause(d_model=args.d_model)
    train(model, train_set, args.epochs, args.lr)

    report = evaluate(model, test_set)
    print(f"\n=== 测试集根因排序评测（{report['num_events']} 事件）===")
    print(f"{'metric':<8}{'heuristic':>12}{'tgat':>10}")
    for metric in ("top1", "top3", "mrr"):
        h = report["heuristic"][metric]
        d = report["tgat"][metric]
        print(f"{metric:<8}{h:>12.3f}{d:>10.3f}   Δ{d-h:+.3f}")

    if args.model_dir:
        args.model_dir.mkdir(parents=True, exist_ok=True)
        save_path = args.model_dir / "tgat.pt"
        torch.save({"model_state": model.state_dict()}, save_path)
        print(f"\n模型 → {save_path}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"明细 → {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

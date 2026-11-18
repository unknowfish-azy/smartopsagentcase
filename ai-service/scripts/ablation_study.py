"""P2 消融实验：量化各感知模块的真实价值。

核心设计——让"静态方法失效"的场景：
  故障沿调用链传播，**根因 severity 随机（不一定最高），下游被传染节点告警可能更严重**。
  这是真实运维常态（如 redis 慢是根因但只 P1，下游 gateway 超时反而 P0）。
  - 静态方法（单快照 GAT / severity+度 heuristic）：易被高 severity 的下游节点误导
  - TGAT（多切片 + 时间维）：能靠"谁最早异常"定位真根因

对比组：
  A. heuristic（severity+degree 加权，静态）
  B. 静态 GAT（只用最终快照）
  C. TGAT（多切片 + 时间 GRU）
指标：top1 / top3 / MRR（根因排序）

另含 trace 消融：heuristic vs traceformer（span 级 F1 / PR-AUC）。

用法：
    python scripts/ablation_study.py --num-events 200 --epochs 60
    python scripts/ablation_study.py --json reports/ablation.json
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
    heuristic_tgat_scores,
    snapshot_edge_index,
    snapshot_features,
)
from app.training.graph_model import RootCauseGAT  # noqa: E402

SERVICES = ["gateway", "order", "user", "payment", "mysql", "redis", "cache", "mq", "search"]
SEVERITIES = ["P0", "P1", "P2"]


# ---------------------------------------------------------------------------
# 故障传播场景（根因 severity 随机 → 静态方法失效）
# ---------------------------------------------------------------------------

def generate_spread_events(num_events: int, seed: int = 42) -> list[dict]:
    rng = np.random.default_rng(seed)
    events = []
    for _ in range(num_events):
        chain_len = int(rng.integers(3, 6))
        chain = list(rng.choice(SERVICES, size=chain_len, replace=False))
        root_idx = int(rng.integers(1, chain_len))
        num_snaps = int(rng.integers(3, 5))

        snapshots = []
        for k in range(num_snaps):
            nodes = []
            for i, svc in enumerate(chain):
                if i == root_idx:
                    infected = k >= 1
                elif i < root_idx:
                    infected = k >= num_snaps - 1
                else:
                    infected = (i - root_idx) <= (k - 1)
                # 关键：severity 与是否根因**无关**，纯随机 → 静态方法无法靠 severity 定位
                sev = str(rng.choice(SEVERITIES)) if infected else "P3"
                status = "OPEN" if infected else "CLOSED"
                nodes.append({"alert_id": svc, "severity": sev, "status": status})
            edges = [{"alert_a_id": chain[i], "alert_b_id": chain[i + 1]} for i in range(chain_len - 1)]
            snapshots.append({"timestamp": 100.0 * (k + 1), "nodes": nodes, "edges": edges})
        events.append({"snapshots": snapshots, "root_id": chain[root_idx]})
    return events


def _prepare(event: dict):
    snaps = event["snapshots"]
    node_order = align_nodes(snaps)
    feats, masks, eis = [], [], []
    for s in snaps:
        x, m = snapshot_features(s, node_order)
        feats.append(x)
        masks.append(m)
        eis.append(snapshot_edge_index(s, node_order))
    labels = np.asarray([1.0 if nid == event["root_id"] else 0.0 for nid in node_order], dtype=np.float32)
    return feats, eis, masks, labels, node_order


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


def _acc(acc: dict, r: dict) -> None:
    for k in acc:
        acc[k].append(r[k])


# ---------------------------------------------------------------------------
# 三组模型
# ---------------------------------------------------------------------------

def train_tgat(events, epochs, lr, seed):
    import torch
    torch.manual_seed(seed)
    model = TGATRootCause()
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    prepared = [_prepare(e) for e in events]
    for _ in range(epochs):
        model.train()
        for feats, eis, masks, labels, _ in prepared:
            snaps = [(torch.as_tensor(feats[k]), torch.as_tensor(eis[k], dtype=torch.long), torch.as_tensor(masks[k]))
                     for k in range(len(feats))]
            y = torch.as_tensor(labels)
            opt.zero_grad()
            loss = torch.nn.BCELoss()(model(snaps), y)
            loss.backward()
            opt.step()
    return model


def train_static_gat(events, epochs, lr, seed):
    """静态 GAT：只用每个事件的**最终快照**训练（无时间信息）。"""
    import torch
    torch.manual_seed(seed)
    model = RootCauseGAT(in_channels=3, hidden_channels=32, heads=2)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    prepared = [_prepare(e) for e in events]
    for _ in range(epochs):
        model.train()
        for feats, eis, masks, labels, _ in prepared:
            x = torch.as_tensor(feats[-1])                        # 最终快照
            ei = torch.as_tensor(eis[-1], dtype=torch.long)
            y = torch.as_tensor(labels)
            opt.zero_grad()
            scores = model(x, ei)                                 # [N]（已 sigmoid）
            loss = torch.nn.BCELoss()(scores, y)
            loss.backward()
            opt.step()
    return model


def run_tgat_ablation(train_set, test_set, epochs, lr, seed) -> dict:
    import torch
    tgat = train_tgat(train_set, epochs, lr, seed)
    gat = train_static_gat(train_set, epochs, lr, seed)

    res = {"heuristic": {"top1": [], "top3": [], "mrr": []},
           "static_gat": {"top1": [], "top3": [], "mrr": []},
           "tgat": {"top1": [], "top3": [], "mrr": []}}
    tgat.eval(); gat.eval()
    with torch.no_grad():
        for e in test_set:
            feats, eis, masks, labels, _ = _prepare(e)
            snaps = [(feats[k], eis[k], masks[k]) for k in range(len(feats))]
            # A. heuristic（多切片，severity+degree，静态加权）
            _acc(res["heuristic"], _ranking(heuristic_tgat_scores(feats, masks), labels))
            # B. 静态 GAT（最终快照）
            x = torch.as_tensor(feats[-1]); ei = torch.as_tensor(eis[-1], dtype=torch.long)
            _acc(res["static_gat"], _ranking(gat(x, ei).numpy(), labels))
            # C. TGAT（多切片 + 时间）
            _acc(res["tgat"], _ranking(tgat.predict(snaps), labels))

    return {name: {k: float(np.mean(v)) for k, v in metrics.items()} for name, metrics in res.items()}


# ---------------------------------------------------------------------------
# trace 消融（heuristic vs traceformer）
# ---------------------------------------------------------------------------

def run_trace_ablation(seed) -> dict:
    import torch
    from app.training.trace_model import TraceFormer, build_feature_matrix, heuristic_span_scores
    from scripts.train_trace import generate_traces, _labels

    traces = generate_traces(200, seed=seed)[160:]  # 用与训练不同的种子段做测试
    model = TraceFormer()
    ckpt_path = Path(__file__).resolve().parents[1] / "models" / "traceformer.pt"
    if ckpt_path.exists():
        model.load_state_dict(torch.load(ckpt_path, map_location="cpu")["model_state"])
    model.eval()

    def f1(s, l):
        p = (s >= 0.5).astype(np.float32)
        tp = float(((p == 1) & (l == 1)).sum()); fp = float(((p == 1) & (l == 0)).sum()); fn = float(((p == 0) & (l == 1)).sum())
        prec = tp / max(tp + fp, 1e-9); rec = tp / max(tp + fn, 1e-9)
        return float(2 * prec * rec / max(prec + rec, 1e-9))

    ms, hs, ys = [], [], []
    with torch.no_grad():
        for tr in traces:
            spans = tr["spans"]; y = _labels(spans)
            ms.append(model.predict_scores(build_feature_matrix(spans)))
            hs.append(heuristic_span_scores(spans)); ys.append(y)
    ms = np.concatenate(ms); hs = np.concatenate(hs); ys = np.concatenate(ys)
    return {"heuristic_f1": f1(hs, ys), "traceformer_f1": f1(ms, ys), "num_spans": int(ys.size)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--num-events", type=int, default=200)
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    events = generate_spread_events(args.num_events, seed=args.seed)
    split = int(len(events) * 0.8)
    train_set, test_set = events[:split], events[split:]
    print(f"动态拓扑消融：events={len(events)} (train={len(train_set)} test={len(test_set)})")
    print("场景：根因 severity 随机（静态方法失效），故障沿调用链传播\n")

    tgat_res = run_tgat_ablation(train_set, test_set, args.epochs, args.lr, args.seed)
    print("=== 动态拓扑根因消融（top1/top3/MRR）===")
    print(f"{'metric':<8}{'heuristic':>12}{'static_gat':>13}{'tgat':>9}")
    for metric in ("top1", "top3", "mrr"):
        h = tgat_res["heuristic"][metric]; g = tgat_res["static_gat"][metric]; t = tgat_res["tgat"][metric]
        print(f"{metric:<8}{h:>12.3f}{g:>13.3f}{t:>9.3f}   Δ(tgat-gat){t-g:+.3f}")

    print("\n=== 调用链 Trace 消融（span 级 F1）===")
    trace_res = run_trace_ablation(args.seed)
    print(f"heuristic_f1={trace_res['heuristic_f1']:.3f}  traceformer_f1={trace_res['traceformer_f1']:.3f}  "
          f"(spans={trace_res['num_spans']})")

    report = {"dynamic_topology": tgat_res, "trace": trace_res,
              "config": {"num_events": args.num_events, "epochs": args.epochs, "seed": args.seed}}
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\n明细 → {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

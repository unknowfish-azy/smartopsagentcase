"""P0-2 GCN 根因定位训练脚本。

任务：给定关联告警图（correlation_event 的 alert 们 + correlation_edge 的关联），
      对每个节点预测 root_cause_probability，top-3 作为候选根因。

数据来源优先级：
  1. 真实 sentinel_alert + correlation_edge 表（如果后端数据库接了）
  2. --mock 模式：脚本生成模拟告警 + 拓扑边，训练 GCN 验证链路

用法：
    python scripts/train_p02_rootcause_gcn.py --mock               # mock 数据训练评测
    python scripts/train_p02_rootcause_gcn.py --mock --epochs 80 --model-dir ../data/models/rootcause_gcn
    python scripts/train_p02_rootcause_gcn.py --model-path <real_db.py>  # 真实数据（待实现）

评测指标：
  - Top-1 Hit Rate（根因节点是否排第一）
  - Top-3 Hit Rate（根因节点是否进前三）
  - MRR（Mean Reciprocal Rank）

这些指标专门针对"排序任务"，比单纯 accuracy 更有意义。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.training.graph_model import (  # noqa: E402
    RootCauseGCN,
    RootCauseGCNConfig,
    GraphSample,
    heuristic_rootcause_score,
    available,
    get_variant_class,
    RootCauseGAT,  # noqa: F401 — 让 torch.load 能反序列化
)


MODE = available()


# ---------------------------------------------------------------------------
# Mock 数据生成器（模拟 correlation_event + sentinel_alert_correlation_edge 结构）
# ---------------------------------------------------------------------------

SEVERITIES = ["P0", "P1", "P2", "P3"]
STATUSES = ["OPEN", "OPEN", "OPEN", "PENDING_APPROVAL"]  # OPEN 多一些
METRIC_TYPES = ["cpu", "memory", "disk", "network", "db_conn", "gc_pause"]
SERVERS = ["srv-web-01", "srv-web-02", "srv-api-01", "srv-db-01", "srv-cache-01"]


def generate_mock_correlation_events(
    num_events: int = 20,
    seed: int = 17,
    avg_alerts_per_event: tuple[int, int] = (4, 12),
) -> list[GraphSample]:
    """生成模拟 correlation_event + sentinel_alert_correlation_edge。

    结构对齐真实表：
      - 节点 = sentinel_alert（severity, status, metric, server, value）
      - 边 = sentinel_alert_correlation_edge（lift_score / co_fires / correlation_type）
      - 标签 = correlation_event.root_cause_alert_id（模拟：同 server 里第一个 P0/P1 告警）
    """
    rng = np.random.default_rng(seed)
    samples: list[GraphSample] = []

    for event_idx in range(num_events):
        # 随机选一组服务器（模拟同资源组）
        group_size = int(rng.integers(2, 4))
        group_servers = list(rng.choice(SERVERS, size=group_size, replace=False))

        # 随机生成该 event 里的告警
        num_alerts = int(rng.integers(avg_alerts_per_event[0], avg_alerts_per_event[1] + 1))
        severities = rng.choice(SEVERITIES, size=num_alerts, p=[0.05, 0.15, 0.4, 0.4])
        statuses = rng.choice(STATUSES, size=num_alerts)
        metrics = rng.choice(METRIC_TYPES, size=num_alerts)
        servers = rng.choice(group_servers, size=num_alerts)
        values = rng.uniform(0.5, 5.0, size=num_alerts)

        # 特征：severity_ordinal + status_ordinal + value_norm
        sev_ord = np.array([SEVERITIES.index(s) for s in severities], dtype=float)
        sta_ord = np.array([0 if s == "OPEN" else 1 for s in statuses], dtype=float)
        val_norm = values / max(values.max(), 1.0)
        features = np.column_stack([sev_ord, sta_ord, val_norm])

        # 边生成：同 server 的告警两两相连 + 同 metric 跨 server 相连
        srcs: list[int] = []
        dsts: list[int] = []
        weights: list[float] = []
        for i in range(num_alerts):
            for j in range(i + 1, num_alerts):
                if servers[i] == servers[j]:
                    srcs.extend([i, j])
                    dsts.extend([j, i])
                    # 同 server 边权强
                    lift = float(rng.uniform(1.2, 3.5))
                    weights.extend([lift, lift])
                elif metrics[i] == metrics[j]:
                    srcs.extend([i, j])
                    dsts.extend([j, i])
                    # 同 metric 跨 server 弱一点
                    lift = float(rng.uniform(0.8, 2.0))
                    weights.extend([lift, lift])

        if not srcs:
            # 至少加一条边（孤立节点 GCN 没法消息传递）
            if num_alerts >= 2:
                srcs = [0, 1]
                dsts = [1, 0]
                weights = [1.0, 1.0]

        edge_index = np.array([srcs, dsts], dtype=np.int64) if srcs else np.zeros((2, 0), dtype=np.int64)
        edge_weight = np.array(weights, dtype=np.float32) if weights else None

        # 标签：同 server 里 severity 最高的告警当 root cause（模拟真实关联逻辑）
        # severity P0=0 是最小 ordinal，但 P0 最严重 → 反向映射
        sev_rank = np.array([len(SEVERITIES) - 1 - SEVERITIES.index(s) for s in severities])
        # 只标记每个 server 里最高 rank 的那个告警（可能多个 server 各一个）
        labels = np.zeros(num_alerts, dtype=np.int64)
        for server in group_servers:
            mask = servers == server
            if mask.sum() == 0:
                continue
            server_local = np.where(mask)[0]
            best_idx = server_local[sev_rank[server_local].argmax()]
            labels[best_idx] = 1  # 多个 server 时可能多个 root cause（罕见但存在）

        # 限制单 event 的 root cause 不超过 1（评测时取第一个即可）
        if labels.sum() > 1:
            # 随机保留一个，或保留 P0 的那个
            keep_idx = np.where(labels == 1)[0][0]
            labels = np.zeros(num_alerts, dtype=np.int64)
            labels[keep_idx] = 1

        node_ids = [f"evt{event_idx}_a{i}" for i in range(num_alerts)]

        samples.append(GraphSample(
            node_features=features,
            edge_index=edge_index,
            edge_weight=edge_weight,
            labels=labels,
            node_ids=node_ids,
            metric_names=metrics.tolist(),
            server_names=servers.tolist(),
        ))

    return samples


# ---------------------------------------------------------------------------
# 训练 + 评测
# ---------------------------------------------------------------------------

def train_one_sample(model, sample: GraphSample, config: RootCauseGCNConfig) -> float:
    """单 event 上训练几步，返回 loss（不跨 event 共享权重——每个图独立预测）。"""
    import torch

    model.train()
    x = torch.tensor(sample.node_features, dtype=torch.float32)
    ei = torch.tensor(sample.edge_index, dtype=torch.int64)
    ew = torch.tensor(sample.edge_weight, dtype=torch.float32) if sample.edge_weight is not None else None
    y = torch.tensor(sample.labels, dtype=torch.float32)

    optimizer = torch.optim.Adam(model.parameters(), lr=config.lr)
    pos_idx = torch.where(y == 1)[0]
    neg_idx = torch.where(y == 0)[0]
    # 加权 BCE：正样本少，加 pos_weight 让模型更重视根因
    loss_fn = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(config.pos_weight))

    final_loss = 0.0
    for _ in range(config.epochs):
        optimizer.zero_grad()
        scores = model(x, ei, ew)
        # BCE 需要 logits，模型已经 sigmoid 了 → 用 BCELoss
        loss = torch.nn.BCELoss()(scores, y)
        loss.backward()
        optimizer.step()
        final_loss = float(loss.item())

    return final_loss


def evaluate_ranking(scores: np.ndarray, labels: np.ndarray) -> dict[str, float]:
    """排序评测：top-1 hit、top-3 hit、MRR。"""
    n = len(scores)
    if n == 0 or labels.sum() == 0:
        return {"top1_hit": 0.0, "top3_hit": 0.0, "mrr": 0.0}

    # 所有 root cause 标签的位置（1-indexed，按 score 从高到低排）
    ranked_order = np.argsort(-scores)
    ranks: list[int] = []
    for idx in range(n):
        if labels[ranked_order[idx]] == 1:
            ranks.append(idx + 1)  # 1-indexed

    # 至少一个 root cause
    top1_hit = 1.0 if any(r == 1 for r in ranks) else 0.0
    top3_hit = 1.0 if any(r <= 3 for r in ranks) else 0.0
    mrr = float(np.mean([1.0 / r for r in ranks])) if ranks else 0.0

    return {"top1_hit": top1_hit, "top3_hit": top3_hit, "mrr": mrr}


def run_benchmark(
    samples: list[GraphSample],
    config: RootCauseGCNConfig,
) -> dict[str, Any]:
    """对每个 event：先训练 GCN → 再预测 → 评排序指标。

    同 bench_d3 基线对比口径：用 heuristic 当 baseline。
    """
    # baseline（heuristic：度越高越可疑）
    heuristic_ranks = {"top1_hit": [], "top3_hit": [], "mrr": []}
    for s in samples:
        degree = np.zeros(s.node_features.shape[0])
        if s.edge_index.shape[1] > 0:
            for k in range(s.node_features.shape[0]):
                degree[k] = (s.edge_index[0] == k).sum() + (s.edge_index[1] == k).sum()
        h_scores = heuristic_rootcause_score(s.node_features.shape[0], degree)
        result = evaluate_ranking(h_scores, s.labels)
        for key in heuristic_ranks:
            heuristic_ranks[key].append(result[key])

    # GCN / GAT（按 config.variant 选择）
    deep_ranks = {"top1_hit": [], "top3_hit": [], "mrr": []}
    deep_losses: list[float] = []

    if MODE != "heuristic":
        import torch

        ModelCls = get_variant_class(config.variant)
        variant_name = config.variant.upper()
        print(f"\n  deep variant={variant_name}")

        for s in samples:
            torch.manual_seed(config.seed)
            if config.variant == "gat":
                model = ModelCls(
                    in_channels=config.in_channels,
                    hidden_channels=config.hidden_channels,
                    heads=config.gat_heads,
                    dropout=config.dropout,
                )
            else:
                model = ModelCls(
                    in_channels=config.in_channels,
                    hidden_channels=config.hidden_channels,
                )
            loss = train_one_sample(model, s, config)
            deep_losses.append(loss)

            model.eval()
            with torch.no_grad():
                x = torch.tensor(s.node_features, dtype=torch.float32)
                ei = torch.tensor(s.edge_index, dtype=torch.int64)
                ew = torch.tensor(s.edge_weight, dtype=torch.float32) if s.edge_weight is not None else None
                scores = model(x, ei, ew).numpy()

            result = evaluate_ranking(scores, s.labels)
            for key in deep_ranks:
                deep_ranks[key].append(result[key])

    results: dict[str, Any] = {
        "mode": MODE,
        "variant": config.variant,
        "num_events": len(samples),
        "heuristic": {
            name: float(np.mean(vals)) for name, vals in heuristic_ranks.items() if vals
        },
    }
    if deep_ranks["top1_hit"]:
        results[config.variant] = {
            name: float(np.mean(vals)) for name, vals in deep_ranks.items()
        }
        results[config.variant]["avg_loss"] = float(np.mean(deep_losses)) if deep_losses else None
        base_mrr = results["heuristic"]["mrr"]
        variant_mrr = results[config.variant]["mrr"]
        results[config.variant]["mrr_delta"] = round(variant_mrr - base_mrr, 4)
    return results


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mock", action="store_true", help="用 mock 数据训练评测")
    parser.add_argument("--num-events", type=int, default=20)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--hidden-dim", type=int, default=16)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--variant", choices=["gcn", "gat"], default="gat", help="GCN(P0-2) 或 GAT(P1-1)，默认 gat")
    parser.add_argument("--gat-heads", type=int, default=2, help="GAT 多头数（variant=gat 时有效）")
    parser.add_argument("--dropout", type=float, default=0.3)
    parser.add_argument("--model-dir", type=Path, default=None, help="保存 .pt（可选）")
    parser.add_argument("--json", type=Path, default=None, help="评测明细 JSON 输出")
    args = parser.parse_args(argv)

    print(f"mode={MODE}  variant={args.variant}")

    if args.mock:
        samples = generate_mock_correlation_events(num_events=args.num_events)
        print(f"generated {len(samples)} mock correlation events")
    else:
        print("⚠️  真实数据库读取尚未实现，当前请用 --mock 模式")
        return 1

    config = RootCauseGCNConfig(
        epochs=args.epochs,
        hidden_channels=args.hidden_dim,
        lr=args.lr,
        variant=args.variant,
        gat_heads=args.gat_heads,
        dropout=args.dropout,
    )
    report = run_benchmark(samples, config)

    # 打印
    print(f"\n评测汇总（{report['num_events']} 个 event, variant={report['variant']}）")
    deep_col = report["variant"].upper()
    print(f"{'metric':<15}{'heuristic':>12}{deep_col:>12}{'Δ':>8}")
    for metric in ("top1_hit", "top3_hit", "mrr"):
        h = report["heuristic"].get(metric, 0.0)
        d = report.get(args.variant, {}).get(metric, None)
        delta = f"{d - h:>+8.3f}" if d is not None else "  —  "
        print(f"{metric:<15}{h:>12.3f}{str(d):>12}{delta}")

    if report.get(args.variant, {}).get("avg_loss") is not None:
        print(f"\n{deep_col} avg_loss = {report[args.variant]['avg_loss']:.4f}")

    # 保存 .pt（按 variant 选模型类，写入 variant 字段让推理服务识别）
    if args.model_dir and MODE != "heuristic":
        import torch
        args.model_dir.mkdir(parents=True, exist_ok=True)
        ModelCls = get_variant_class(args.variant)
        if args.variant == "gat":
            model = ModelCls(in_channels=3, hidden_channels=args.hidden_dim, heads=args.gat_heads, dropout=args.dropout)
        else:
            model = ModelCls(in_channels=3, hidden_channels=args.hidden_dim)
        save_path = args.model_dir / "rootcause_gcn.pt"
        torch.save({
            "variant": args.variant,          # ← 推理服务靠这个字段判断是 GCN 还是 GAT
            "hidden_channels": args.hidden_dim,
            "gat_heads": args.gat_heads,
            "dropout": args.dropout,
            "model_state": model.state_dict(),
        }, save_path)
        print(f"\n模型 ({args.variant.upper()}) → {save_path}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"明细 → {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

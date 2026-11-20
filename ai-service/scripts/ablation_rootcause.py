# -*- coding: utf-8 -*-
"""M2-3 根因模型消融实验：模型 × 场景 × 指标 矩阵。

对比组（6 个模型）：
  heuristic   度+severity+value 加权（无模型基线）
  gcn         2 层 GCN（M0 主干）
  gat         2 层 GAT 多头（M0 主干）
  graphsage   2 层 GraphSAGE（M2-3 新增，大图采样友好）
  tgat        时序图（多切片+GRU，M2 已有）
  tgpm        时序-图融合（M2-3 新增，节点特征融入时序统计）

场景维度（4 类）：
  static_sev_random   静态拓扑，根因 severity 随机（静态方法失效）
  dynamic_spread      故障沿调用链传播，多快照
  large_graph         大图（50+ 节点），测试 GraphSAGE 采样优势
  rootcause_degraded  模拟根因服务降级（部分节点特征缺失）

指标：A@1 / A@3 / MRR（根因排序），重复 repeats 次取均值±std。

产出：
  reports/ablation_rootcause_raw.json      原始逐次结果
  reports/ablation_rootcause_summary.json  聚合统计
  reports/ablation_rootcause_matrix.csv    模型×场景矩阵
  reports/ablation_rootcause_report.txt    人类可读报告

用法：
    python scripts/ablation_rootcause.py
    python scripts/ablation_rootcause.py --num-events 300 --repeats 5 --epochs 80
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.training.graph_model import (  # noqa: E402
    RootCauseGAT,
    RootCauseGCN,
    RootCauseGraphSAGE,
    get_variant_class,
)
from app.training.tgat_model import (  # noqa: E402
    TGATRootCause,
    align_nodes as tgat_align,
    heuristic_tgat_scores,
    snapshot_edge_index,
    snapshot_features,
)
from app.training.tgpm_model import (  # noqa: E402
    TGPMRootCause,
    fused_features,
    heuristic_tgpm_scores,
)

SERVICES = [
    "gateway", "order", "user", "payment", "mysql", "redis",
    "cache", "mq", "search", "auth", "log", "monitor",
]
SEVERITIES = ["P0", "P1", "P2", "P3"]

# ---------------------------------------------------------------------------
# 模型预设表（经验 2344982：用预设表替代分散 if/else）
# ---------------------------------------------------------------------------

MODEL_PRESETS = {
    "heuristic": {"needs_train": False, "static": True},
    "gcn": {"needs_train": True, "static": True, "variant": "gcn"},
    "gat": {"needs_train": True, "static": True, "variant": "gat"},
    "graphsage": {"needs_train": True, "static": True, "variant": "graphsage"},
    "tgat": {"needs_train": True, "static": False},
    "tgpm": {"needs_train": True, "static": False},
}

SCENARIO_PRESETS = (
    "static_sev_random",
    "dynamic_spread",
    "large_graph",
    "rootcause_degraded",
)

METRICS = ("a1", "a3", "mrr")


# ---------------------------------------------------------------------------
# 场景生成器
# ---------------------------------------------------------------------------


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def gen_static_sev_random(rng, n_events: int) -> list[dict]:
    """静态拓扑：根因 severity 随机，静态方法易被高 severity 下游误导。"""
    events = []
    for _ in range(n_events):
        chain_len = int(rng.integers(3, 7))
        chain = list(rng.choice(SERVICES, size=chain_len, replace=False))
        root_idx = int(rng.integers(1, chain_len))
        nodes = []
        for i, svc in enumerate(chain):
            # 根因 severity 随机；下游可能更严重
            sev = str(rng.choice(SEVERITIES))
            status = "OPEN" if i >= root_idx else "CLOSED"
            nodes.append({"alert_id": svc, "severity": sev, "status": status, "value": float(rng.random())})
        edges = [{"alert_a_id": chain[i], "alert_b_id": chain[i + 1]} for i in range(chain_len - 1)]
        events.append({"snapshots": [{"nodes": nodes, "edges": edges}], "root_id": chain[root_idx]})
    return events


def gen_dynamic_spread(rng, n_events: int) -> list[dict]:
    """故障沿调用链传播，多快照（根因最先异常）。"""
    events = []
    for _ in range(n_events):
        chain_len = int(rng.integers(4, 8))
        chain = list(rng.choice(SERVICES, size=chain_len, replace=False))
        root_idx = int(rng.integers(1, chain_len))
        num_snaps = int(rng.integers(4, 7))
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
                sev = str(rng.choice(SEVERITIES)) if infected else "P3"
                status = "OPEN" if infected else "CLOSED"
                nodes.append({"alert_id": svc, "severity": sev, "status": status})
            edges = [{"alert_a_id": chain[i], "alert_b_id": chain[i + 1]} for i in range(chain_len - 1)]
            snapshots.append({"timestamp": 100.0 * (k + 1), "nodes": nodes, "edges": edges})
        events.append({"snapshots": snapshots, "root_id": chain[root_idx]})
    return events


def gen_large_graph(rng, n_events: int) -> list[dict]:
    """大图场景：50-80 节点，随机 DAG 拓扑，根因是入度为 0 的源头节点（传播起点）。"""
    events = []
    for _ in range(n_events):
        n_nodes = int(rng.integers(50, 81))
        node_ids = [f"node-{i}" for i in range(n_nodes)]
        # 随机 DAG：每个节点连 1-3 个前驱（编号更小的节点）
        edges = []
        in_degree = np.zeros(n_nodes, dtype=int)
        for i in range(1, n_nodes):
            n_pred = int(rng.integers(1, 4))
            preds = rng.choice(range(i), size=min(n_pred, i), replace=False)
            for p in preds:
                edges.append({"alert_a_id": node_ids[p], "alert_b_id": node_ids[i]})
                in_degree[i] += 1
        # 根因 = 入度为 0 的源头节点中随机选一个（传播起点）
        sources = np.where(in_degree == 0)[0]
        root_idx = int(rng.choice(sources)) if len(sources) > 0 else 0
        # 从根因开始 BFS 标记"被传染"节点（模拟故障传播）
        infected = {root_idx}
        queue = [root_idx]
        adj = {i: [] for i in range(n_nodes)}
        for e in edges:
            a = node_ids.index(e["alert_a_id"])
            b = node_ids.index(e["alert_b_id"])
            adj[a].append(b)
        while queue:
            cur = queue.pop(0)
            for nxt in adj[cur]:
                if nxt not in infected:
                    infected.add(nxt)
                    queue.append(nxt)
        nodes = []
        for i, nid in enumerate(node_ids):
            is_infected = i in infected
            sev = str(rng.choice(SEVERITIES)) if is_infected else "P3"
            status = "OPEN" if is_infected else "CLOSED"
            nodes.append({"alert_id": nid, "severity": sev, "status": status})
        events.append({"snapshots": [{"nodes": nodes, "edges": edges}], "root_id": node_ids[root_idx]})
    return events


def gen_rootcause_degraded(rng, n_events: int) -> list[dict]:
    """模拟根因服务降级：30% 节点特征缺失（severity/status 置 None）。"""
    events = gen_static_sev_random(rng, n_events)
    for event in events:
        snap = event["snapshots"][0]
        for node in snap["nodes"]:
            if rng.random() < 0.3:
                node["severity"] = None
                node["status"] = None
    return events


SCENARIO_GENERATORS = {
    "static_sev_random": gen_static_sev_random,
    "dynamic_spread": gen_dynamic_spread,
    "large_graph": gen_large_graph,
    "rootcause_degraded": gen_rootcause_degraded,
}


# ---------------------------------------------------------------------------
# 特征构造（静态模型用最终快照）
# ---------------------------------------------------------------------------


def _static_features(snap: dict) -> tuple[np.ndarray, np.ndarray, list[str]]:
    nodes = snap["nodes"]
    edges = snap["edges"]
    id_map = {n["alert_id"]: i for i, n in enumerate(nodes)}
    n = len(nodes)
    sev = np.zeros(n, dtype=np.float32)
    firing = np.zeros(n, dtype=np.float32)
    vals = np.zeros(n, dtype=np.float32)
    for i, node in enumerate(nodes):
        s = node.get("severity")
        sev[i] = {"P0": 1.0, "P1": 0.75, "P2": 0.5, "P3": 0.25}.get(str(s or "P2").upper(), 0.5)
        firing[i] = 1.0 if str(node.get("status", "OPEN")).lower() in {"open", "pending_approval", "remediating"} else 0.0
        vals[i] = float(node.get("value") or 0.0)
    degree = np.zeros(n, dtype=np.float32)
    src, dst = [], []
    for e in edges:
        a, b = e.get("alert_a_id"), e.get("alert_b_id")
        if a in id_map and b in id_map:
            ia, ib = id_map[a], id_map[b]
            src += [ia, ib]
            dst += [ib, ia]
            degree[ia] += 1
            degree[ib] += 1
    max_deg = float(degree.max()) or 1.0
    x = np.column_stack([sev, firing, degree / max_deg]).astype(np.float32)
    ei = np.asarray([src, dst], dtype=np.int64) if src else np.zeros((2, 0), dtype=np.int64)
    return x, ei, [n["alert_id"] for n in nodes]


def _ranking(scores: np.ndarray, root_idx: int) -> dict:
    if len(scores) == 0:
        return {"a1": 0.0, "a3": 0.0, "mrr": 0.0}
    order = np.argsort(-scores)
    rank = int(np.where(order == root_idx)[0][0]) + 1
    return {"a1": 1.0 if rank == 1 else 0.0, "a3": 1.0 if rank <= 3 else 0.0, "mrr": 1.0 / rank}


# ---------------------------------------------------------------------------
# 模型训练与评估
# ---------------------------------------------------------------------------


def train_static_model(variant, train_events, epochs, lr, seed):
    import torch
    torch.manual_seed(seed)
    cls = get_variant_class(variant)
    model = cls(in_channels=3, hidden_channels=32)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    prepared = []
    for e in train_events:
        x, ei, ids = _static_features(e["snapshots"][-1])
        labels = np.asarray([1.0 if nid == e["root_id"] else 0.0 for nid in ids], dtype=np.float32)
        prepared.append((x, ei, labels))
    for _ in range(epochs):
        model.train()
        for x, ei, labels in prepared:
            xt = torch.as_tensor(x)
            eit = torch.as_tensor(ei, dtype=torch.long)
            y = torch.as_tensor(labels)
            opt.zero_grad()
            scores = model(xt, eit)
            loss = torch.nn.BCELoss()(scores, y)
            loss.backward()
            opt.step()
    model.eval()
    return model


def eval_static_model(model, event):
    import torch
    x, ei, ids = _static_features(event["snapshots"][-1])
    root_idx = ids.index(event["root_id"])
    with torch.no_grad():
        scores = model(torch.as_tensor(x), torch.as_tensor(ei, dtype=torch.long)).numpy()
    return _ranking(scores, root_idx)


def heuristic_static_scores(event):
    snap = event["snapshots"][-1]
    nodes = snap["nodes"]
    edges = snap["edges"]
    id_map = {n["alert_id"]: i for i, n in enumerate(nodes)}
    n = len(nodes)
    degree = np.zeros(n, dtype=float)
    for e in edges:
        a, b = e.get("alert_a_id"), e.get("alert_b_id")
        if a in id_map:
            degree[id_map[a]] += 1
        if b in id_map:
            degree[id_map[b]] += 1
    sev_w = np.array([{"P0": 4, "P1": 3, "P2": 2, "P3": 1}.get(str(nd.get("severity") or "P2").upper(), 2) for nd in nodes])
    deg_norm = degree / max(degree.max(), 1e-6)
    scores = 0.4 * deg_norm + 0.4 * (sev_w / sev_w.max()) + 0.2 * np.random.rand(n) * 0.1
    root_idx = [i for i, nd in enumerate(nodes) if nd["alert_id"] == event["root_id"]][0]
    return _ranking(scores, root_idx)


def train_tgat(train_events, epochs, lr, seed):
    import torch
    torch.manual_seed(seed)
    model = TGATRootCause()
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    prepared = []
    for e in train_events:
        snaps = e["snapshots"]
        order = tgat_align(snaps)
        feats, masks, eis = [], [], []
        for s in snaps:
            x, m = snapshot_features(s, order)
            feats.append(x)
            masks.append(m)
            eis.append(snapshot_edge_index(s, order))
        labels = np.asarray([1.0 if nid == e["root_id"] else 0.0 for nid in order], dtype=np.float32)
        prepared.append((feats, eis, masks, labels))
    for _ in range(epochs):
        model.train()
        for feats, eis, masks, labels in prepared:
            snaps = [(torch.as_tensor(feats[k]), torch.as_tensor(eis[k], dtype=torch.long), torch.as_tensor(masks[k]))
                     for k in range(len(feats))]
            y = torch.as_tensor(labels)
            opt.zero_grad()
            loss = torch.nn.BCELoss()(model(snaps), y)
            loss.backward()
            opt.step()
    model.eval()
    return model


def eval_tgat(model, event):
    snaps = event["snapshots"]
    order = tgat_align(snaps)
    root_idx = order.index(event["root_id"])
    feats, masks, eis = [], [], []
    for s in snaps:
        x, m = snapshot_features(s, order)
        feats.append(x)
        masks.append(m)
        eis.append(snapshot_edge_index(s, order))
    snaps_t = [(np.asarray(feats[k]), np.asarray(eis[k]), np.asarray(masks[k])) for k in range(len(feats))]
    scores = model.predict(snaps_t)
    return _ranking(scores, root_idx)


def heuristic_tgat_eval(event):
    snaps = event["snapshots"]
    order = tgat_align(snaps)
    root_idx = order.index(event["root_id"])
    feats, masks = [], []
    for s in snaps:
        x, m = snapshot_features(s, order)
        feats.append(x)
        masks.append(m)
    scores = heuristic_tgat_scores(feats, masks)
    return _ranking(scores, root_idx)


def train_tgpm(train_events, epochs, lr, seed, backbone="gcn"):
    import torch
    torch.manual_seed(seed)
    model = TGPMRootCause(backbone=backbone)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    prepared = []
    for e in train_events:
        snaps = e["snapshots"]
        order = tgat_align(snaps)
        x, ei = fused_features(snaps, order)
        labels = np.asarray([1.0 if nid == e["root_id"] else 0.0 for nid in order], dtype=np.float32)
        prepared.append((x, ei, labels))
    for _ in range(epochs):
        model.train()
        for x, ei, labels in prepared:
            xt = torch.as_tensor(x)
            eit = torch.as_tensor(ei, dtype=torch.long)
            y = torch.as_tensor(labels)
            opt.zero_grad()
            scores = model(xt, eit)
            loss = torch.nn.BCELoss()(scores, y)
            loss.backward()
            opt.step()
    model.eval()
    return model


def eval_tgpm(model, event):
    snaps = event["snapshots"]
    order = tgat_align(snaps)
    root_idx = order.index(event["root_id"])
    scores = model.predict(snaps, order)
    return _ranking(scores, root_idx)


def heuristic_tgpm_eval(event):
    snaps = event["snapshots"]
    order = tgat_align(snaps)
    root_idx = order.index(event["root_id"])
    scores = heuristic_tgpm_scores(snaps, order)
    return _ranking(scores, root_idx)


# ---------------------------------------------------------------------------
# 单次消融运行
# ---------------------------------------------------------------------------


def run_once(scenario, model_name, train_events, test_events, epochs, lr, seed) -> dict:
    t0 = time.time()
    preset = MODEL_PRESETS[model_name]
    if model_name == "heuristic":
        results = [heuristic_static_scores(e) for e in test_events]
    elif model_name in ("gcn", "gat", "graphsage"):
        model = train_static_model(preset["variant"], train_events, epochs, lr, seed)
        results = [eval_static_model(model, e) for e in test_events]
    elif model_name == "tgat":
        if scenario == "static_sev_random" or scenario == "large_graph" or scenario == "rootcause_degraded":
            # 静态场景对 TGAT 不公平——给每个事件复制 3 份相同快照模拟"多切片"
            for e in train_events + test_events:
                if len(e["snapshots"]) == 1:
                    e["snapshots"] = [e["snapshots"][0]] * 3
        model = train_tgat(train_events, epochs, lr, seed)
        results = [eval_tgat(model, e) for e in test_events]
    elif model_name == "tgpm":
        if scenario == "static_sev_random" or scenario == "large_graph" or scenario == "rootcause_degraded":
            for e in train_events + test_events:
                if len(e["snapshots"]) == 1:
                    e["snapshots"] = [e["snapshots"][0]] * 3
        model = train_tgpm(train_events, epochs, lr, seed)
        results = [eval_tgpm(model, e) for e in test_events]
    else:
        raise ValueError(model_name)
    elapsed = time.time() - t0
    return {
        "model": model_name,
        "scenario": scenario,
        "seed": seed,
        "a1": float(np.mean([r["a1"] for r in results])),
        "a3": float(np.mean([r["a3"] for r in results])),
        "mrr": float(np.mean([r["mrr"] for r in results])),
        "elapsed_sec": round(elapsed, 3),
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--num-events", type=int, default=200)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--models", nargs="*", default=list(MODEL_PRESETS))
    parser.add_argument("--scenarios", nargs="*", default=list(SCENARIO_PRESETS))
    args = parser.parse_args(argv)

    out_dir = Path(__file__).resolve().parents[1].parent / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "ablation_rootcause_raw.json"
    summary_path = out_dir / "ablation_rootcause_summary.json"
    csv_path = out_dir / "ablation_rootcause_matrix.csv"
    report_path = out_dir / "ablation_rootcause_report.txt"

    raw_runs: list[dict] = []
    for scenario in args.scenarios:
        gen = SCENARIO_GENERATORS[scenario]
        for rep in range(args.repeats):
            seed = args.seed + rep * 1000
            rng = _rng(seed)
            events = gen(rng, args.num_events)
            split = int(len(events) * 0.8)
            train_set, test_set = events[:split], events[split:]
            # 深拷贝避免多模型间快照被修改（tgat/tgpm 会补快照）
            import copy
            train_copy = copy.deepcopy(train_set)
            test_copy = copy.deepcopy(test_set)
            for model_name in args.models:
                run = run_once(
                    scenario, model_name,
                    copy.deepcopy(train_copy), copy.deepcopy(test_copy),
                    args.epochs, args.lr, seed,
                )
                raw_runs.append(run)
                print(
                    f"[{scenario}] rep={rep+1}/{args.repeats} {model_name:<10} "
                    f"A@1={run['a1']:.3f} A@3={run['a3']:.3f} MRR={run['mrr']:.3f} "
                    f"({run['elapsed_sec']}s)"
                )

    # 聚合：每个 (model, scenario) 对 → 均值 ± std
    summary: dict[str, dict] = {}
    for run in raw_runs:
        key = f"{run['model']}::{run['scenario']}"
        summary.setdefault(key, {"a1": [], "a3": [], "mrr": [], "elapsed_sec": []})
        for m in METRICS + ("elapsed_sec",):
            summary[key][m].append(run[m])

    agg = {}
    for key, vals in summary.items():
        model, scenario = key.split("::")
        agg.setdefault(model, {})[scenario] = {
            m: {"mean": round(float(np.mean(vals[m])), 4), "std": round(float(np.std(vals[m])), 4)}
            for m in METRICS
        } | {"elapsed_sec": round(float(np.mean(vals["elapsed_sec"])), 3)}

    # 写 raw + summary
    raw_path.write_text(json.dumps({"runs": raw_runs}, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path.write_text(json.dumps(agg, ensure_ascii=False, indent=2), encoding="utf-8")

    # 写 CSV 矩阵（model × scenario，A@1）
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["model"] + list(args.scenarios))
        for model in args.models:
            row = [model]
            for scenario in args.scenarios:
                val = agg.get(model, {}).get(scenario, {}).get("a1", {}).get("mean", "")
                row.append(val)
            writer.writerow(row)

    # 写报告
    lines = []
    lines.append("=" * 78)
    lines.append("M2-3 根因模型消融报告")
    lines.append("=" * 78)
    lines.append(f"场景数: {args.num_events}  重复: {args.repeats}  epochs: {args.epochs}  seed: {args.seed}")
    lines.append("")
    lines.append("模型: " + ", ".join(args.models))
    lines.append("场景: " + ", ".join(args.scenarios))
    lines.append("")

    for scenario in args.scenarios:
        lines.append("-" * 78)
        lines.append(f"场景: {scenario}")
        lines.append("-" * 78)
        lines.append(f"{'model':<12}{'A@1':>10}{'A@3':>10}{'MRR':>10}{'time(s)':>10}")
        for model in args.models:
            entry = agg.get(model, {}).get(scenario, {})
            a1 = entry.get("a1", {}).get("mean", 0)
            a3 = entry.get("a3", {}).get("mean", 0)
            mrr = entry.get("mrr", {}).get("mean", 0)
            t = entry.get("elapsed_sec", 0)
            lines.append(f"{model:<12}{a1:>10.4f}{a3:>10.4f}{mrr:>10.4f}{t:>10.2f}")
        lines.append("")

    # 边际贡献：相对 heuristic 的 A@1 提升
    lines.append("=" * 78)
    lines.append("边际贡献（相对 heuristic 的 A@1 提升）")
    lines.append("=" * 78)
    lines.append(f"{'model':<12}{'static_sev':>12}{'dynamic':>10}{'large':>10}{'degraded':>10}")
    for model in args.models:
        if model == "heuristic":
            continue
        row = [model]
        for scenario in ("static_sev_random", "dynamic_spread", "large_graph", "rootcause_degraded"):
            base = agg.get("heuristic", {}).get(scenario, {}).get("a1", {}).get("mean", 0)
            cur = agg.get(model, {}).get(scenario, {}).get("a1", {}).get("mean", 0)
            row.append(f"{cur - base:+.4f}")
        lines.append(f"{row[0]:<12}{row[1]:>12}{row[2]:>10}{row[3]:>10}{row[4]:>10}")
    lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")

    print("\n" + "\n".join(lines))
    print(f"\n产出:")
    print(f"  raw:     {raw_path}")
    print(f"  summary: {summary_path}")
    print(f"  csv:     {csv_path}")
    print(f"  report:  {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

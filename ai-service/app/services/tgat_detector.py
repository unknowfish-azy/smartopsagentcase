"""P2 阶段 3：TGAT 动态拓扑根因感知推理服务。

输入时间切片图序列，输出跨时间聚合的根因候选 + 异常传播路径 + 拓扑动态变化。
与 rootcause_detector（静态单快照）互补：TGAT 面向 K8s 动态扩缩容、故障传播场景。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

from ..training.tgat_model import (
    _TORCH_AVAILABLE,
    _firing,
    align_nodes,
    available,
    heuristic_tgat_scores,
    snapshot_edge_index,
    snapshot_features,
)


@dataclass
class _TGATState:
    kind: Literal["unavailable", "heuristic", "tgat"] = "unavailable"
    reason: str | None = None
    model: Any = None


_state: _TGATState | None = None

# 默认权重路径：训练脚本 train_tgat.py 保存到 ai-service/models/tgat.pt
DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "tgat.pt"


def init_model(model_path: Path | None = None) -> _TGATState:
    global _state
    state = _TGATState()
    if not _TORCH_AVAILABLE:
        state.kind = "heuristic"
        state.reason = "torch 未安装，降级为 heuristic"
        _state = state
        return state

    model_path = model_path or DEFAULT_MODEL_PATH
    if model_path and model_path.exists():
        try:
            import torch
            from ..training.tgat_model import TGATRootCause

            ckpt = torch.load(model_path, map_location="cpu")
            model = TGATRootCause()
            model.load_state_dict(ckpt["model_state"])
            model.eval()
            state.model = model
            state.kind = "tgat"
        except Exception as exc:
            state.kind = "heuristic"
            state.reason = f"权重加载失败({exc})，降级为 heuristic"
    else:
        state.kind = "heuristic"
        state.reason = "未找到 tgat.pt，降级为 heuristic"
    _state = state
    return state


def get_state() -> _TGATState:
    if _state is None:
        return init_model()
    return _state


def analyze(request) -> dict:
    """主入口：TGATRequest → 跨时间根因候选 + 传播路径 + 拓扑变化。"""
    state = get_state()
    snapshots = [s.model_dump() if hasattr(s, "model_dump") else dict(s) for s in request.snapshots]
    # 按时间升序
    snapshots.sort(key=lambda s: s.get("timestamp", 0.0))
    t = len(snapshots)
    node_order = align_nodes(snapshots)
    n = len(node_order)

    feats, masks, edge_indices = [], [], []
    for snap in snapshots:
        x, m = snapshot_features(snap, node_order)
        feats.append(x)
        masks.append(m)
        edge_indices.append(snapshot_edge_index(snap, node_order))

    # 打分
    if state.kind == "tgat" and state.model is not None:
        try:
            prepared = list(zip(feats, edge_indices, masks))
            scores = state.model.predict(prepared)
            mode = "tgat"
        except Exception:
            scores = heuristic_tgat_scores(feats, masks, request.time_decay)
            mode = "heuristic"
    else:
        scores = heuristic_tgat_scores(feats, masks, request.time_decay)
        mode = "heuristic"

    # 节点元数据（首次/末次出现、峰值切片、最近 severity）
    node_scores = []
    for i, nid in enumerate(node_order):
        seen = [k for k in range(t) if masks[k][i] > 0]
        sev = "P2"
        for k in reversed(seen):
            for node in snapshots[k].get("nodes", []):
                if node.get("alert_id") == nid:
                    sev = str(node.get("severity", "P2")).upper()
                    break
            else:
                continue
            break
        # 首次活跃（firing/OPEN）时间：故障扩散顺序的依据，与根因分解耦
        first_active = 0.0
        for k in seen:
            hit = next((nd for nd in snapshots[k].get("nodes", []) if nd.get("alert_id") == nid), None)
            if hit is not None and _firing(hit):
                first_active = snapshots[k].get("timestamp", 0.0)
                break
        node_scores.append({
            "alert_id": nid,
            "score": round(float(scores[i]), 4),
            "first_seen": snapshots[seen[0]].get("timestamp", 0.0) if seen else 0.0,
            "last_seen": snapshots[seen[-1]].get("timestamp", 0.0) if seen else 0.0,
            "first_active": first_active,
            "peak_snapshot": int(np.argmax([feats[k][i][0] if masks[k][i] else -1 for k in range(t)])),
            "severity": sev,
        })

    root_candidates = sorted(node_scores, key=lambda x: x["score"], reverse=True)[: request.top_k]
    spread_path = _spread_path(node_scores)
    topology_changes = _topology_changes(snapshots, node_order)
    anomaly_score = round(float(np.max(scores)) if n else 0.0, 4)

    explanation = _build_explanation(mode, root_candidates, spread_path, topology_changes)

    return {
        "ok": True,
        "mode": mode,
        "root_candidates": root_candidates,
        "node_scores": node_scores,
        "spread_path": spread_path,
        "topology_changes": topology_changes,
        "anomaly_score": anomaly_score,
        "explanation": explanation,
    }


def _spread_path(node_scores: list[dict]) -> list[str]:
    """异常传播路径：所有**活跃过**（firing/OPEN）的节点按首次活跃时间排序。

    依据节点活跃状态（故障确实发生）而非根因分阈值——真模型只给真根因高分，
    被传染节点根因分低但仍是传播链一环，不能因分数低而丢失。
    """
    active = [x for x in node_scores if x.get("first_active", 0.0) > 0.0]
    active.sort(key=lambda x: (x["first_active"], -x["score"]))
    return [x["alert_id"] for x in active]


def _topology_changes(snapshots: list[dict], node_order: list[str]) -> list[dict]:
    """相邻切片的节点/边增减（K8s 扩缩容、实例上下线的直接证据）。"""
    changes = []
    prev_nodes: set = set()
    prev_edges: set = set()
    for k, snap in enumerate(snapshots):
        cur_nodes = {n.get("alert_id") for n in snap.get("nodes", [])}
        cur_edges = {(e.get("alert_a_id"), e.get("alert_b_id")) for e in snap.get("edges", [])}
        if k > 0:
            added_n = sorted(cur_nodes - prev_nodes)
            removed_n = sorted(prev_nodes - cur_nodes)
            added_e = len(cur_edges - prev_edges)
            removed_e = len(prev_edges - cur_edges)
            if added_n or removed_n or added_e or removed_e:
                changes.append({
                    "snapshot": k,
                    "timestamp": snap.get("timestamp", 0.0),
                    "added_nodes": added_n,
                    "removed_nodes": removed_n,
                    "added_edges": added_e,
                    "removed_edges": removed_e,
                })
        prev_nodes, prev_edges = cur_nodes, cur_edges
    return changes


def _build_explanation(mode, root_candidates, spread_path, topology_changes) -> str:
    parts = [f"[{mode}] 动态拓扑根因分析"]
    if root_candidates:
        top = root_candidates[0]
        parts.append(f"最可疑根因：{top['alert_id']}（{top['score']:.2f}）")
    if spread_path:
        parts.append("传播路径：" + " → ".join(spread_path))
    if topology_changes:
        parts.append(f"拓扑变化 {len(topology_changes)} 次")
    return "；".join(parts)


def get_model_info() -> dict:
    state = get_state()
    return {
        "available": state.kind != "unavailable",
        "kind": state.kind,
        "reason": state.reason,
        "torch_available": _TORCH_AVAILABLE,
        "preferred": available(),
        "dynamic": True,
    }

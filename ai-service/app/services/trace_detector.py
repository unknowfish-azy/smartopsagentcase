"""P2 阶段 2：调用链 Trace 异常感知推理服务。

与 log_classifier / rootcause_detector 同骨架：
- 全局单例（经验 578502：避免重复加载导致 Windows 崩溃）
- 有权重 → TraceFormer；无权重/torch 缺失 → heuristic
- 输出结构化证据（异常分/慢节点/错误节点/关键路径/top-k 可疑 span），决策权交给上层 Agent
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

from ..training.trace_model import (
    _TORCH_AVAILABLE,
    available,
    build_feature_matrix,
    heuristic_span_scores,
)


@dataclass
class _TraceState:
    kind: Literal["unavailable", "heuristic", "traceformer"] = "unavailable"
    reason: str | None = None
    model: Any = None
    max_len: int = 256


_state: _TraceState | None = None

# 默认权重路径：训练脚本 train_trace.py 保存到 ai-service/models/traceformer.pt
DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "traceformer.pt"


def init_model(model_path: Path | None = None) -> _TraceState:
    """加载权重或初始化 fallback（幂等）。未显式传路径时默认探测 models/traceformer.pt。"""
    global _state
    state = _TraceState()

    if not _TORCH_AVAILABLE:
        state.kind = "heuristic"
        state.reason = "torch 未安装，降级为 heuristic"
        _state = state
        return state

    model_path = model_path or DEFAULT_MODEL_PATH
    if model_path and model_path.exists():
        try:
            import torch
            from ..training.trace_model import TraceFormer

            ckpt = torch.load(model_path, map_location="cpu")
            model = TraceFormer(max_len=ckpt.get("max_len", 256))
            model.load_state_dict(ckpt["model_state"])
            model.eval()
            state.model = model
            state.max_len = ckpt.get("max_len", 256)
            state.kind = "traceformer"
        except Exception as exc:
            state.kind = "heuristic"
            state.reason = f"权重加载失败({exc})，降级为 heuristic"
    else:
        state.kind = "heuristic"
        state.reason = "未找到 traceformer.pt，降级为 heuristic"

    _state = state
    return state


def get_state() -> _TraceState:
    if _state is None:
        return init_model()
    return _state


def analyze(request) -> dict:
    """主入口：TraceAnalyzeRequest → 结构化异常证据。"""
    state = get_state()
    spans = [s.model_dump() if hasattr(s, "model_dump") else dict(s) for s in request.spans]
    n = len(spans)

    # 打分
    if state.kind == "traceformer" and state.model is not None and n <= state.max_len:
        try:
            features = build_feature_matrix(spans)
            scores = state.model.predict_scores(features)
            mode = "traceformer"
        except Exception:
            scores = heuristic_span_scores(spans, request.slow_threshold_ms, request.error_status_min)
            mode = "heuristic"
    else:
        scores = heuristic_span_scores(spans, request.slow_threshold_ms, request.error_status_min)
        mode = "heuristic"

    # 逐 span 组装
    span_scores = []
    slow_spans: list[str] = []
    error_spans: list[str] = []
    for i, s in enumerate(spans):
        status = int(s.get("status_code", 200))
        duration = float(s.get("duration_ms", 0.0))
        is_error = bool(s.get("is_error")) or status >= request.error_status_min
        is_slow = duration >= request.slow_threshold_ms
        score = round(float(scores[i]), 4)

        reason_parts = []
        if is_error:
            reason_parts.append(f"错误状态码 {status}")
        if is_slow:
            reason_parts.append(f"慢 span（{duration:.0f}ms ≥ {request.slow_threshold_ms:.0f}ms）")
        if not reason_parts and score >= 0.5:
            reason_parts.append("耗时相对离群")

        span_scores.append({
            "span_id": s.get("span_id", f"span-{i}"),
            "service": s.get("service", ""),
            "operation": s.get("operation", ""),
            "duration_ms": duration,
            "status_code": status,
            "anomaly_score": score,
            "is_slow": is_slow,
            "is_error": is_error,
            "reason": "；".join(reason_parts),
        })
        if is_slow:
            slow_spans.append(s.get("span_id", f"span-{i}"))
        if is_error:
            error_spans.append(s.get("span_id", f"span-{i}"))

    # top-k 可疑 span
    root_candidates = sorted(span_scores, key=lambda x: x["anomaly_score"], reverse=True)[: request.top_k]

    # 关键路径：按耗时主导的服务序列（root → 各下游，取每跳最慢）
    critical_path = _critical_path(spans)

    anomaly_score = round(float(np.max(scores)) if n else 0.0, 4)
    is_anomaly = bool(anomaly_score >= 0.5 or error_spans or slow_spans)

    explanation = _build_explanation(mode, anomaly_score, root_candidates, slow_spans, error_spans)

    return {
        "ok": True,
        "mode": mode,
        "trace_id": request.trace_id,
        "anomaly_score": anomaly_score,
        "is_anomaly": is_anomaly,
        "span_scores": span_scores,
        "slow_spans": slow_spans,
        "error_spans": error_spans,
        "critical_path": critical_path,
        "root_candidates": root_candidates,
        "explanation": explanation,
    }


def _critical_path(spans: list[dict[str, Any]]) -> list[str]:
    """沿 parent 链找耗时最长的 root→leaf 路径，返回服务名序列。"""
    if not spans:
        return []
    by_id = {s.get("span_id"): s for s in spans}
    children: dict[Any, list] = {}
    roots = []
    for s in spans:
        pid = s.get("parent_id")
        if pid and pid in by_id:
            children.setdefault(pid, []).append(s)
        else:
            roots.append(s)

    best_path: list[dict] = []
    best_dur = -1.0

    def dfs(node, path, acc):
        nonlocal best_path, best_dur
        path = path + [node]
        acc = acc + float(node.get("duration_ms", 0.0))
        kids = children.get(node.get("span_id"), [])
        if not kids:
            if acc > best_dur:
                best_dur = acc
                best_path = path
            return
        for k in kids:
            dfs(k, path, acc)

    for r in roots or spans[:1]:
        dfs(r, [], 0.0)

    return [s.get("service", "") or s.get("span_id", "") for s in best_path]


def _build_explanation(mode, anomaly_score, root_candidates, slow_spans, error_spans) -> str:
    parts = [f"[{mode}] 链路异常分 {anomaly_score:.2f}"]
    if error_spans:
        parts.append(f"{len(error_spans)} 个错误 span")
    if slow_spans:
        parts.append(f"{len(slow_spans)} 个慢 span")
    if root_candidates:
        top = root_candidates[0]
        parts.append(f"最可疑：{top['service'] or top['span_id']}（{top['anomaly_score']:.2f}）")
    return "；".join(parts)


def get_model_info() -> dict:
    state = get_state()
    return {
        "available": state.kind != "unavailable",
        "kind": state.kind,
        "reason": state.reason,
        "torch_available": _TORCH_AVAILABLE,
        "preferred": available(),
        "max_len": state.max_len,
    }

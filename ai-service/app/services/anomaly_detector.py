"""P0-1 推理服务：加载模型 + 计算异常分。

设计：
- 全局单例模型（一次加载，多请求复用），跟 llm.py 的 Ollama client 风格一致；
- torch 未安装或权重缺失时，自动 fallback 到 sklearn IsolationForest（anomaly.py 已有的实现）；
- 不做训练：训练走 scripts/train_p01_anomaly_transformer.py，服务只读权重。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

from ..schemas.anomaly import (
    AnomalyPoint,
    AnomalyRequest,
    AnomalyResponse,
    AnomalySpan,
    MetricAnomalyResult,
)


# ---------------------------------------------------------------------------
# 依赖探测（与训练脚本一致，避免 pytest 在无 torch 环境下 ImportError）
# ---------------------------------------------------------------------------

_TORCH_AVAILABLE = False
try:
    import torch  # type: ignore[import-untyped]

    _TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover - 依赖缺失时降级
    pass


# ---------------------------------------------------------------------------
# 模型配置（可被 FastAPI lifespan 里覆盖）
# ---------------------------------------------------------------------------

@dataclass
class _ModelState:
    """服务端持有的全局模型状态。"""

    kind: Literal["unavailable", "isolation_forest_fallback", "anomaly_transformer"] = "unavailable"
    reason: str | None = None
    # deep model 字段
    model: Any = None           # torch.nn.Module 或 None
    window: int = 64
    latent_dim: int = 32
    threshold: float = 0.05     # 异常分阈值
    # fallback 字段
    fallback_config: Any = None  # DetectorConfig


_state: _ModelState | None = None


def init_model(model_path: Path | None = None, window: int = 64) -> _ModelState:
    """服务启动时调用，加载权重或初始化 fallback。

    幂等：重复调用会覆盖 _state。
    """
    global _state
    state = _ModelState(window=window)

    # 1. torch 不可用 → 直接 fallback
    if not _TORCH_AVAILABLE:
        from ..training.anomaly import DetectorConfig  # 延迟导入
        state.kind = "isolation_forest_fallback"
        state.reason = "torch 未安装，降级为 IsolationForest"
        state.fallback_config = DetectorConfig()
        _state = state
        return state

    # 2. 有权重文件 → 加载
    if model_path and model_path.exists():
        try:
            ckpt = torch.load(model_path, map_location="cpu")
            # 从共享模块 import，保证和训练脚本里的类定义完全一致（torch.load 反序列化要求）
            from app.training.anomaly_transformer import AnomalyTransformer

            model = AnomalyTransformer(window=ckpt.get("window", window), latent_dim=ckpt.get("latent_dim", 32))
            model.load_state_dict(ckpt["model_state"])
            model.eval()
            state.model = model
            state.window = ckpt.get("window", window)
            state.latent_dim = ckpt.get("latent_dim", 32)
            state.threshold = ckpt.get("threshold", 0.05)
            state.kind = "anomaly_transformer"
            state.reason = None
        except Exception as exc:
            from ..training.anomaly import DetectorConfig
            state.kind = "isolation_forest_fallback"
            state.reason = f"权重加载失败({exc})，降级为 IsolationForest"
            state.fallback_config = DetectorConfig()
    else:
        # 3. 没给模型路径 → fallback（首次部署场景）
        from ..training.anomaly import DetectorConfig
        state.kind = "isolation_forest_fallback"
        state.reason = "未找到 anomaly_transformer.pt，降级为 IsolationForest"
        state.fallback_config = DetectorConfig()

    _state = state
    return state


def get_state() -> _ModelState:
    if _state is None:
        return init_model()
    return _state


# ---------------------------------------------------------------------------
# 推理入口
# ---------------------------------------------------------------------------

def detect(request: AnomalyRequest) -> AnomalyResponse:
    """主入口：接收 AnomalyRequest，返回 AnomalyResponse。"""
    state = get_state()

    if request.values is None and request.metrics is None:
        return _empty_response(state, request, reason="no-input")

    # 归一化：统一成 metrics dict
    metrics_in: dict[str, list[float]]
    if request.values is not None:
        name = request.metric_name or "single"
        metrics_in = {name: request.values}
    else:
        metrics_in = request.metrics or {}

    results: list[MetricAnomalyResult] = []
    threshold_q = request.threshold_quantile

    for metric_name, raw_values in metrics_in.items():
        values = np.asarray(raw_values, dtype=float)
        scores = _score_one_metric(values, state, request.window)
        is_anomaly = _score_to_binary(scores, threshold_q)

        points = _to_anomaly_points(is_anomaly, scores, metric_name)
        spans = _to_anomaly_spans(is_anomaly, scores)

        results.append(MetricAnomalyResult(
            metric=metric_name,
            points=points,
            spans=spans,
            anomaly_count=len(points),
            span_count=len(spans),
            mean_score=float(scores.mean()) if len(scores) else 0.0,
            peak_score=float(scores.max()) if len(scores) else 0.0,
            kind=state.kind,
        ))

    return AnomalyResponse(
        ok=True,
        mode="multi" if request.metrics else "single",
        model_status="ok" if state.kind == "anomaly_transformer" else "fallback" if state.kind == "isolation_forest_fallback" else "unavailable",
        model_status_detail=state.reason,
        window=request.window or state.window,
        threshold_quantile=threshold_q,
        results=results,
        task_id=request.task_id,
    )


def get_model_info() -> dict:
    """GET /api/nn/model-info 的原始字典（schema 再包一层）。"""
    state = get_state()
    return {
        "available": state.kind != "unavailable",
        "kind": state.kind,
        "reason": state.reason,
        "torch_available": _TORCH_AVAILABLE,
        "window": state.window if state.kind != "unavailable" else None,
        "latent_dim": state.latent_dim if state.kind == "anomaly_transformer" else None,
    }


# ---------------------------------------------------------------------------
# 内部：评分 + 阈值 + 聚合
# ---------------------------------------------------------------------------

def _score_one_metric(values: np.ndarray, state: _ModelState, window: int) -> np.ndarray:
    """返回长度 = len(values) 的逐点异常分。"""
    n = len(values)
    if n == 0:
        return np.array([], dtype=float)

    if state.kind == "anomaly_transformer" and _TORCH_AVAILABLE:
        return _score_deep(values, state, window)
    # fallback：IsolationForest（复用 anomaly.py 的 detect_isolation_forest，取 score_samples 原始分）
    return _score_isolation_forest(values, state)


def _score_deep(values: np.ndarray, state: _ModelState, window: int) -> np.ndarray:
    """滑动窗口送进 AnomalyTransformer，聚合逐点 MSE。"""
    model = state.model
    if model is None:
        return np.zeros(len(values))

    model_window = state.window
    if len(values) < model_window:
        return np.zeros(len(values))

    # 切窗口（step=1 保证逐点覆盖）
    n_windows = len(values) - model_window + 1
    windows = np.lib.stride_tricks.sliding_window_view(values, model_window).copy()

    with torch.no_grad():
        x = torch.tensor(windows, dtype=torch.float32)
        recon = model(x).numpy()

    # 逐窗口 MSE
    window_error = np.mean((windows - recon) ** 2, axis=1)  # (n_windows,)

    # 聚合回原长度：每个位置出现在多个窗口里，平均
    scores = np.zeros(len(values))
    counts = np.zeros(len(values))
    for i, err in enumerate(window_error):
        scores[i : i + model_window] += err
        counts[i : i + model_window] += 1
    return np.divide(scores, np.maximum(counts, 1))


def _score_isolation_forest(values: np.ndarray, state: _ModelState) -> np.ndarray:
    """降级路径：sklearn IsolationForest 的 score_samples（越低越异常）。"""
    try:
        from sklearn.ensemble import IsolationForest
        from ..training.anomaly import _features

        features = _features(values, window=10)
        model = IsolationForest(n_estimators=100, contamination=0.05, random_state=17)
        model.fit(features)
        raw = model.score_samples(features)  # 越大越正常
        # 反转为"越大越异常"，方便统一阈值逻辑
        return -raw
    except Exception:
        return np.zeros(len(values))


def _score_to_binary(scores: np.ndarray, threshold_quantile: float) -> np.ndarray:
    """按阈值分位二值化。"""
    if len(scores) == 0:
        return np.array([], dtype=bool)
    threshold = float(np.quantile(scores, threshold_quantile))
    return scores > threshold


def _to_anomaly_points(is_anomaly: np.ndarray, scores: np.ndarray, metric: str) -> list[AnomalyPoint]:
    return [
        AnomalyPoint(index=int(i), score=float(scores[i]), metric=metric)
        for i in range(len(is_anomaly)) if is_anomaly[i]
    ]


def _to_anomaly_spans(is_anomaly: np.ndarray, scores: np.ndarray) -> list[AnomalySpan]:
    """把连续 True 聚合成 span，避免 Agent 拿到碎片点位。"""
    spans: list[AnomalySpan] = []
    i = 0
    n = len(is_anomaly)
    while i < n:
        if not is_anomaly[i]:
            i += 1
            continue
        j = i
        while j < n and is_anomaly[j]:
            j += 1
        seg_scores = scores[i:j]
        spans.append(AnomalySpan(
            start=int(i),
            end=int(j - 1),
            point_count=int(j - i),
            avg_score=float(seg_scores.mean()),
        ))
        i = j
    return spans


def _empty_response(state: _ModelState, request: AnomalyRequest, reason: str) -> AnomalyResponse:
    return AnomalyResponse(
        ok=False,
        mode="single",
        model_status="fallback" if state.kind == "isolation_forest_fallback" else "unavailable" if state.kind == "unavailable" else "ok",
        model_status_detail=f"无输入: {reason}",
        window=request.window or state.window,
        threshold_quantile=request.threshold_quantile,
        results=[],
        task_id=request.task_id,
        extra={"reason": reason},
    )

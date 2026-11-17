"""P1-4 自适应阈值推理服务。

和 anomaly_detector.py 不同：
- 那边走 AnomalyTransformer + IsolationForest，不知道周期性；
- 这里走 STL 分解 + ACF 周期推断，把 seasonality 剥掉再判异常。
- 依赖 statsmodels，缺了就退化（但退化路径下 adaptive_threshold ≈ rolling_z，seasonal_ewma ≈ ewma）。
"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np

from ..training.anomaly import (
    DetectorConfig,
    DETECTOR_NAMES,
    detect_all,
    _ewma,
)


# ---------------------------------------------------------------------------
# 依赖探测
# ---------------------------------------------------------------------------

_STATS_MODELS_AVAILABLE = False
try:
    from statsmodels.tsa.seasonal import STL  # noqa: F401

    _STATS_MODELS_AVAILABLE = True
except ImportError:
    STL = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Service 主入口
# ---------------------------------------------------------------------------

def get_model_info() -> dict[str, Any]:
    """GET /api/nn/adaptive-threshold-info。"""
    return {
        "available": True,  # 即使 statsmodels 缺了也有退化路径
        "kind": "stl" if _STATS_MODELS_AVAILABLE else "degraded",
        "reason": None if _STATS_MODELS_AVAILABLE else "statsmodels 未安装，退化至 rolling_z + ewma",
        "statsmodels_available": _STATS_MODELS_AVAILABLE,
        "inference_method": "stl_decomposition_residual_zscore",
        "note": (
            "P1-4 自适应阈值：STL 季节分解 + residual z-score。"
            "解决 '白天高/凌晨低' 导致固定阈值误报漏报的问题。"
        ),
    }


def detect(request) -> dict[str, Any]:
    """主入口：返回两个自适应检测器的结果 + 周期推断 + 可视化基线。"""
    values = np.asarray(request.values, dtype=float)

    # 1. 确定 calibration / values
    if request.calibration is not None:
        calibration = np.asarray(request.calibration, dtype=float)
    else:
        # 从 values 切：前 2/3 calibration，后 1/3 values
        split = max(len(values) // 3, 24)  # calibration 至少 24 点
        # 切完后剩余作为 values
        calibration = values[:split].copy()
        values = values[split:].copy()

    if len(calibration) < 12:
        # calibration 太短，直接退化
        config = DetectorConfig(k=request.k, window=request.window, alpha=request.alpha, contamination=request.contamination)
        results = detect_all(values, calibration, config)
        return _build_response(
            request=request,
            values=values,
            calibration=calibration,
            results=results,
            mode="degraded_rolling",
            degraded_reason=f"calibration 太短 ({len(calibration)} < 12)",
            inferred_period=None,
            period_source="unavailable",
            seasonal_profile=[],
            baseline_track=[],
        )

    # 2. 构造 config → detect_all → 只取两个自适应检测器
    config = DetectorConfig(k=request.k, window=request.window, alpha=request.alpha, contamination=request.contamination)
    results = detect_all(values, calibration, config)

    # 3. 周期推断
    inferred_period, period_source, seasonal_profile, baseline_track = _run_stl(
        calibration, values, request.force_period
    )

    if _STATS_MODELS_AVAILABLE and seasonal_profile is not None:
        mode = "stl"
        degraded_reason = None
    elif _STATS_MODELS_AVAILABLE:
        # STL 可用但 period 推断失败 → 退化到 rolling_z/ewma（但 detect_all 返回的也是退化结果）
        mode = "degraded_rolling"
        degraded_reason = "period 推断失败，退化至 rolling_z + ewma"
    else:
        mode = "degraded_rolling"
        degraded_reason = "statsmodels 未安装"

    return _build_response(
        request=request,
        values=values,
        calibration=calibration,
        results=results,
        mode=mode,
        degraded_reason=degraded_reason,
        inferred_period=inferred_period,
        period_source=period_source,
        seasonal_profile=seasonal_profile or [],
        baseline_track=baseline_track or [],
    )


# ---------------------------------------------------------------------------
# STL 执行 + 周期推断（暴露 seasonal_profile / baseline_track 给前端）
# ---------------------------------------------------------------------------

def _run_stl(
    calibration: np.ndarray,
    values: np.ndarray,
    force_period: int | None,
) -> tuple[int | None, Literal["acf", "force", "unavailable"], list[float] | None, list[float] | None]:
    """调 STL，返回 (inferred_period, source, seasonal_profile, baseline_track)。

    baseline_track 是 adaptive_threshold 检测器内部用的 "EWMA(deseasonalized)"——
    这是 Agent/前端画"自适应基线"需要的，detect_all 只返回 bool mask 没有这个。
    """
    if not _STATS_MODELS_AVAILABLE:
        return None, "unavailable", None, None

    # period 推断：force_period 优先，否则 ACF
    period: int | None = None
    source: Literal["acf", "force", "unavailable"]

    if force_period is not None:
        period = force_period
        source = "force"
    else:
        period = _infer_period(calibration)
        source = "acf" if period is not None else "unavailable"

    if period is None or period >= max(len(calibration) - 1, 8):
        return None, source, None, None

    # STL 分解 calibration
    try:
        stl = STL(calibration, period=period, robust=True)
        res = stl.fit()
        seasonal_profile = res.seasonal[:period].copy()

        # 外推 seasonal 到 values 长度
        seasonal_vals = np.tile(seasonal_profile, len(values) // period + 1)[: len(values)]

        # baseline_track = EWMA(values - seasonal) —— adaptive_threshold 的基线
        deseasonalized = values - seasonal_vals
        baseline_track = _ewma(deseasonalized, alpha=0.2) + seasonal_vals

        return int(period), source, seasonal_profile.tolist(), baseline_track.tolist()
    except Exception:
        return None, source, None, None


def _infer_period(values: np.ndarray, max_period: int = 48) -> int | None:
    """ACF 找第一个显著峰值（和 anomaly.py 里的 _infer_period 逻辑一致）。"""
    if len(values) < 32:
        return None
    centered = values - values.mean()
    acf = np.correlate(centered, centered, mode="full")[len(centered) - 1 :]
    acf = acf / (acf[0] + 1e-9)
    for lag in range(2, min(max_period, len(acf) - 1)):
        if acf[lag] > acf[lag - 1] and acf[lag] > acf[lag + 1] and acf[lag] > 0.25:
            return lag
    return None


# ---------------------------------------------------------------------------
# 响应组装
# ---------------------------------------------------------------------------

def _aggregate_spans(binary_mask: np.ndarray) -> list[dict[str, int]]:
    """把连续 True 聚合成 span，和 anomaly_detector 风格一致。"""
    spans: list[dict[str, int]] = []
    i = 0
    n = len(binary_mask)
    while i < n:
        if not binary_mask[i]:
            i += 1
            continue
        j = i
        while j < n and binary_mask[j]:
            j += 1
        spans.append({"start": int(i), "end": int(j - 1), "point_count": int(j - i)})
        i = j
    return spans


def _build_response(
    *,
    request,
    values: np.ndarray,
    calibration: np.ndarray,
    results: dict[str, np.ndarray],
    mode: Literal["stl", "degraded_rolling", "degraded_ewma"],
    degraded_reason: str | None,
    inferred_period: int | None,
    period_source: Literal["acf", "force", "unavailable"],
    seasonal_profile: list[float],
    baseline_track: list[float],
) -> dict[str, Any]:
    """拼出最终响应 dict。"""
    # 只取两个自适应检测器
    adaptive_mask = np.asarray(results.get("adaptive_threshold", np.zeros(len(values), dtype=bool)), dtype=bool)
    seasonal_ewma_mask = np.asarray(results.get("seasonal_ewma", np.zeros(len(values), dtype=bool)), dtype=bool)

    # 退化时 fallback 列表
    fallback_names = ["rolling_z", "ewma", "three_sigma", "mad", "rolling_mad", "isolation_forest"]
    fallback_available = [n for n in fallback_names if n in DETECTOR_NAMES]

    return {
        "ok": True,
        "mode": mode,
        "degraded_reason": degraded_reason,
        "inferred_period": inferred_period,
        "period_source": period_source,
        "calibration_mean": float(calibration.mean()) if len(calibration) else 0.0,
        "calibration_std": float(calibration.std(ddof=0)) if len(calibration) else 0.0,
        "calibration_len": len(calibration),
        "seasonal_profile": seasonal_profile,
        "baseline_track": baseline_track,
        "adaptive_threshold": {
            "detector": "adaptive_threshold",
            "binary_mask": adaptive_mask.tolist(),
            "anomaly_count": int(adaptive_mask.sum()),
            "spans": _aggregate_spans(adaptive_mask),
        },
        "seasonal_ewma": {
            "detector": "seasonal_ewma",
            "binary_mask": seasonal_ewma_mask.tolist(),
            "anomaly_count": int(seasonal_ewma_mask.sum()),
            "spans": _aggregate_spans(seasonal_ewma_mask),
        },
        "fallback_detectors_available": fallback_available,
    }

"""PatchTST 时序预测服务：点预测、残差近似区间与趋势风险证据。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np

from ..training.patchtst_model import _TORCH_AVAILABLE, available, normalize_series


@dataclass
class _ForecastState:
    kind: Literal["unavailable", "fallback", "patchtst"] = "unavailable"
    reason: str | None = None
    model: Any = None
    context_length: int | None = None
    horizon: int | None = None
    normalization: dict = field(default_factory=dict)
    residual_std: list[float] = field(default_factory=list)


_state: _ForecastState | None = None
DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "patchtst.pt"


def init_model(model_path: Path | None = None) -> _ForecastState:
    """加载 PatchTST checkpoint；任何失败都显式降级，不伪造神经模型状态。"""
    global _state
    state = _ForecastState()
    if not _TORCH_AVAILABLE:
        state.kind = "fallback"
        state.reason = "torch 未安装，降级为 linear/seasonal_naive"
        _state = state
        return state

    model_path = model_path or DEFAULT_MODEL_PATH
    if not model_path.exists():
        state.kind = "fallback"
        state.reason = "未找到 patchtst.pt，降级为 linear/seasonal_naive"
        _state = state
        return state

    try:
        import torch
        from ..training.patchtst_model import PatchTST

        checkpoint = torch.load(model_path, map_location="cpu")
        normalization = checkpoint["normalization"]
        if normalization.get("method") != "mean_std":
            raise ValueError("仅支持 mean_std 归一化 checkpoint")
        model = PatchTST(**checkpoint["config"])
        model.load_state_dict(checkpoint["model_state"])
        model.eval()
        residual_std = [float(v) for v in checkpoint["residual_std"]]
        if len(residual_std) != model.horizon:
            raise ValueError("residual_std 长度与模型 horizon 不一致")
        state.model = model
        state.context_length = model.context_length
        state.horizon = model.horizon
        state.normalization = normalization
        state.residual_std = residual_std
        state.kind = "patchtst"
    except Exception as exc:
        state.kind = "fallback"
        state.reason = f"权重加载失败({exc})，降级为 linear/seasonal_naive"

    _state = state
    return state


def get_state() -> _ForecastState:
    return _state or init_model()


def _linear_forecast(values: np.ndarray, horizon: int) -> tuple[np.ndarray, np.ndarray, float]:
    context = values[-min(len(values), 64):]
    x = np.arange(len(context), dtype=np.float64)
    design = np.column_stack([x, np.ones(len(context))])
    slope, intercept = np.linalg.lstsq(design, context, rcond=None)[0]
    fitted = design @ np.array([slope, intercept])
    base_std = max(float(np.sqrt(np.mean((context - fitted) ** 2))), 1e-6)
    future_x = np.arange(len(context), len(context) + horizon, dtype=np.float64)
    prediction = slope * future_x + intercept
    residual_std = base_std * np.sqrt(np.arange(1, horizon + 1))
    return prediction, residual_std, float(slope)


def _seasonal_forecast(
    values: np.ndarray, horizon: int, period: int,
) -> tuple[np.ndarray, np.ndarray, float]:
    season = values[-period:]
    prediction = np.asarray([season[i % period] for i in range(horizon)], dtype=np.float64)
    residuals = values[period:] - values[:-period]
    base_std = max(float(np.sqrt(np.mean(residuals ** 2))), 1e-6)
    residual_std = base_std * np.sqrt(np.arange(1, horizon + 1))
    slope = float(np.polyfit(np.arange(horizon), prediction, 1)[0]) if horizon > 1 else 0.0
    return prediction, residual_std, slope


def _trend_and_risk(
    values: np.ndarray,
    prediction: np.ndarray,
    residual_std: np.ndarray,
    slope: float,
    upper_threshold: float | None,
    lower_threshold: float | None,
) -> tuple[str, float, str, list[str]]:
    scale = max(float(values.std()), 1e-6)
    trend_delta = slope * max(len(prediction) - 1, 1)
    if abs(trend_delta) <= 0.1 * scale:
        trend = "stable"
    else:
        trend = "rising" if slope > 0 else "falling"

    trend_strength = min(abs(prediction[-1] - values[-1]) / (2.0 * scale), 1.0)
    uncertainty = min(float(np.mean(residual_std)) / (2.0 * scale), 1.0)
    risk_score = 0.65 * trend_strength + 0.35 * uncertainty
    basis = [
        f"预测末端相对最后观测值变化 {prediction[-1] - values[-1]:.4g}",
        f"残差近似标准差均值 {float(np.mean(residual_std)):.4g}",
    ]

    breach_ratio = 0.0
    if upper_threshold is not None:
        breaches = prediction >= upper_threshold
        breach_ratio = max(breach_ratio, float(breaches.mean()))
        if breaches.any():
            first = int(np.argmax(breaches)) + 1
            basis.append(f"第 {first} 步起预测值达到或超过上限 {upper_threshold}")
    if lower_threshold is not None:
        breaches = prediction <= lower_threshold
        breach_ratio = max(breach_ratio, float(breaches.mean()))
        if breaches.any():
            first = int(np.argmax(breaches)) + 1
            basis.append(f"第 {first} 步起预测值达到或低于下限 {lower_threshold}")
    if upper_threshold is not None or lower_threshold is not None:
        risk_score = max(risk_score, breach_ratio)
    else:
        basis.append("未提供业务上下限，风险分仅反映趋势变化与不确定性，不代表故障或恶化概率")

    risk_score = round(float(np.clip(risk_score, 0.0, 1.0)), 4)
    risk_level = "high" if risk_score >= 0.67 else "medium" if risk_score >= 0.33 else "low"
    return trend, risk_score, risk_level, basis


def forecast(request) -> dict:
    state = get_state()
    values = np.asarray(request.values, dtype=np.float64)
    horizon = request.horizon
    detail = state.reason
    use_model = state.kind == "patchtst" and state.model is not None

    if use_model and len(values) < int(state.context_length or 0):
        use_model = False
        detail = f"历史长度 {len(values)} 小于 PatchTST 上下文 {state.context_length}，降级为统计预测"
    if use_model and horizon > int(state.horizon or 0):
        use_model = False
        detail = f"预测 horizon={horizon} 超过模型训练的 {state.horizon}，降级为统计预测"

    residual_std: np.ndarray
    if use_model:
        try:
            normalized, center, scale = normalize_series(
                values[-state.context_length:],
                eps=float(state.normalization.get("eps", 1e-6)),
            )
            normalized_prediction = state.model.predict_normalized(normalized, horizon)
            prediction = normalized_prediction * scale + center
            residual_std = np.asarray(state.residual_std[:horizon], dtype=np.float64) * scale
            slope = (
                float(np.polyfit(np.arange(horizon), prediction, 1)[0])
                if horizon > 1 else float(prediction[0] - values[-1])
            )
            mode = "patchtst"
        except Exception as exc:
            use_model = False
            detail = f"PatchTST 推理失败({exc})，降级为统计预测"

    if not use_model:
        if request.seasonal_period > 1 and len(values) >= request.seasonal_period * 2:
            prediction, residual_std, slope = _seasonal_forecast(values, horizon, request.seasonal_period)
            mode = "seasonal_naive"
        else:
            prediction, residual_std, slope = _linear_forecast(values, horizon)
            mode = "linear"

    prediction = np.asarray(prediction, dtype=np.float64)
    residual_std = np.maximum(np.asarray(residual_std, dtype=np.float64), 1e-6)
    lower = prediction - 1.96 * residual_std
    upper = prediction + 1.96 * residual_std
    trend, risk_score, risk_level, risk_basis = _trend_and_risk(
        values, prediction, residual_std, slope, request.upper_threshold, request.lower_threshold,
    )

    points = [
        {
            "step": i + 1,
            "value": round(float(prediction[i]), 6),
            "lower": round(float(lower[i]), 6),
            "upper": round(float(upper[i]), 6),
        }
        for i in range(horizon)
    ]
    explanation = (
        f"[{mode}] 未来 {horizon} 点趋势为 {trend}，末端预测 {prediction[-1]:.4g}，"
        f"启发式风险 {risk_level}（{risk_score:.2f}）；区间为 95% 残差正态近似。"
    )
    return {
        "ok": True,
        "mode": mode,
        "model_status": "ok" if mode == "patchtst" else "fallback",
        "model_status_detail": detail if mode != "patchtst" else None,
        "metric_name": request.metric_name,
        "horizon": horizon,
        "points": points,
        "trend": trend,
        "trend_slope": round(slope, 6),
        "risk_score": risk_score,
        "risk_level": risk_level,
        "risk_basis": risk_basis,
        "interval_level": 0.95,
        "interval_method": "gaussian_residual_approximation",
        "explanation": explanation,
    }


def get_model_info() -> dict:
    state = get_state()
    return {
        "available": state.kind != "unavailable",
        "kind": state.kind,
        "reason": state.reason,
        "torch_available": _TORCH_AVAILABLE,
        "preferred": available(),
        "context_length": state.context_length,
        "horizon": state.horizon,
        "normalization": state.normalization or None,
    }

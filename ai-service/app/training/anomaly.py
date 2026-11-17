"""D3 异常检测基线：指标时序上的 5 个检测器与统一的评测口径。

设计约束（来自数据现状）：

- 标签极度稀疏：`sentinel_metric_sample.abnormal` 全库仅 19 个正例，
  其中落在评测段的只有 11 个。因此这里同时支持"真标签评测"和"确定性注入评测"，
  注入评测用来确认结论不是几颗样本的偶然。
- 必须因果：线上只能看到当前和历史点。除 ``three_sigma`` / ``mad`` 使用校准段
  一次性统计外，``rolling_z`` / ``ewma`` / ``isolation_forest`` 都只用过去数据。
- 校准段排除已标注的正例，避免把要检测的东西算进"正常分布"。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

DETECTOR_NAMES = (
    "three_sigma",
    "mad",
    "rolling_z",
    "rolling_mad",
    "ewma",
    "isolation_forest",
    # P1-4 新增：自适应阈值
    "adaptive_threshold",   # STL 分解 → residual z-score
    "seasonal_ewma",        # EWMA baseline 跟随 seasonal
)


@dataclass(frozen=True)
class DetectorConfig:
    """检测器超参。默认值刻意保守，先求低误报。"""

    k: float = 3.0
    window: int = 20
    alpha: float = 0.3
    contamination: float = 0.05


def _empty(size: int) -> np.ndarray:
    return np.zeros(size, dtype=bool)


def detect_three_sigma(
    values: np.ndarray, calibration: np.ndarray, config: DetectorConfig
) -> np.ndarray:
    """基线：校准段均值 ± kσ，双侧判定。"""
    sigma = calibration.std(ddof=0)
    if sigma == 0:
        return _empty(len(values))
    return np.abs(values - calibration.mean()) > config.k * sigma


def detect_mad(
    values: np.ndarray, calibration: np.ndarray, config: DetectorConfig
) -> np.ndarray:
    """稳健基线：中位数 ± k·1.4826·MAD，对厚尾/离群校准点不敏感。"""
    median = np.median(calibration)
    mad = np.median(np.abs(calibration - median))
    scale = 1.4826 * mad
    if scale == 0:
        return _empty(len(values))
    return np.abs(values - median) > config.k * scale


def detect_rolling_z(values: np.ndarray, config: DetectorConfig) -> np.ndarray:
    """因果滚动 z 分数：用前 window 个点估计均值/方差，第 window 个点开始判定。"""
    result = _empty(len(values))
    for index in range(config.window, len(values)):
        history = values[index - config.window : index]
        sigma = history.std(ddof=0)
        if sigma == 0:
            continue
        result[index] = abs(values[index] - history.mean()) > config.k * sigma
    return result


def detect_rolling_mad(values: np.ndarray, config: DetectorConfig) -> np.ndarray:
    """因果滚动 MAD：窗口内中位数 ± k·1.4826·MAD，抗单点尖峰污染。"""
    result = _empty(len(values))
    for index in range(config.window, len(values)):
        history = values[index - config.window : index]
        median = np.median(history)
        scale = 1.4826 * np.median(np.abs(history - median))
        if scale == 0:
            continue
        result[index] = abs(values[index] - median) > config.k * scale
    return result


def detect_ewma(
    values: np.ndarray, calibration: np.ndarray, config: DetectorConfig
) -> np.ndarray:
    """因果 EWMA：偏离指数平滑基线超过 k 倍校准段标准差即告警。"""
    sigma = calibration.std(ddof=0)
    if sigma == 0:
        return _empty(len(values))
    level = float(calibration[-1]) if len(calibration) else float(values[0])
    result = _empty(len(values))
    for index, value in enumerate(values):
        result[index] = abs(value - level) > config.k * sigma
        level = config.alpha * value + (1 - config.alpha) * level
    return result


def _features(values: np.ndarray, window: int = 10) -> np.ndarray:
    """IsolationForest 的输入：当前值、一阶差分、历史滚动均值/标准差。"""
    values = np.asarray(values, dtype=float)
    diff = np.zeros(len(values))
    diff[1:] = np.diff(values)
    rolling_mean = np.zeros(len(values))
    rolling_std = np.zeros(len(values))
    for index in range(len(values)):
        start = max(0, index - window)
        history = values[start:index]
        if len(history):
            rolling_mean[index] = history.mean()
            rolling_std[index] = history.std(ddof=0)
    return np.column_stack([values, diff, rolling_mean, rolling_std])


def detect_isolation_forest(
    values: np.ndarray, calibration: np.ndarray, config: DetectorConfig
) -> np.ndarray:
    """无监督离群检测：只用校准段拟合，阈值取校准分数的 ``contamination`` 分位。"""
    try:
        from sklearn.ensemble import IsolationForest
    except ImportError:  # pragma: no cover - 依赖缺失时退化为全不告警
        return _empty(len(values))

    calibration_features = _features(calibration, config.window)
    features = _features(values, config.window)
    model = IsolationForest(
        n_estimators=100,
        contamination=config.contamination,
        random_state=17,
    )
    model.fit(calibration_features)
    threshold = np.quantile(model.score_samples(calibration_features), config.contamination)
    return model.score_samples(features) < threshold


def detect_adaptive_threshold(
    values: np.ndarray, calibration: np.ndarray, config: DetectorConfig
) -> np.ndarray:
    """P1-4: STL 季节分解 + residual 上做 z-score。

    核心思路（解决"白天高/凌晨低"导致的固定阈值误报/漏报）：
      STL 分解 → trend + seasonal + residual
      阈值只看 residual（真实偏差），不受 seasonality 影响。
      校准段用来算 residual 的正常 σ，阈值 = k * σ。

    依赖 statsmodels STL；缺省时退化为 rolling_z（和 rolling_z 等价）。
    """
    try:
        from statsmodels.tsa.seasonal import STL
    except ImportError:
        return detect_rolling_z(values, config)

    # 找合适的 period——从 calibration 的自相关推断
    period = _infer_period(calibration)
    if period is None or period >= max(len(calibration) - 1, 8):
        # 样本太少或周期太长，退化为 rolling_z
        return detect_rolling_z(values, config)

    # STL 分解 calibration（用 calibration 估 seasonal + trend）
    try:
        stl = STL(calibration, period=period, robust=True)
        res_cal = stl.fit()
        # 把 calibration 的 seasonal profile 当模板，外推到 values
        seasonal_profile = res_cal.seasonal[:period]
        # values 的 seasonal 用 profile 循环拼接
        seasonal_vals = np.tile(seasonal_profile, len(values) // period + 1)[: len(values)]
        # 去掉 seasonal 后的 residual —— 这才是"真实变化"
        deseasonalized = values - seasonal_vals
        # calibration 的 residual 标准差当阈值
        residual_sigma = res_cal.resid.std(ddof=0)
        if residual_sigma < 1e-9:
            return _empty(len(values))
        # 在 deseasonalized 上做滚动 baseline（局部 EWMA），再看偏离
        baseline = _ewma(deseasonalized, alpha=config.alpha)
        return np.abs(deseasonalized - baseline) > config.k * residual_sigma
    except Exception:
        return detect_rolling_z(values, config)


def detect_seasonal_ewma(
    values: np.ndarray, calibration: np.ndarray, config: DetectorConfig
) -> np.ndarray:
    """P1-4: 让 EWMA 的 baseline 跟着 seasonal 走。

    和 detect_adaptive_threshold 类似但更简洁：
      baseline = EWMA(values) + seasonal_profile
      deviation = |values - baseline| / sigma_seasonal
    """
    try:
        from statsmodels.tsa.seasonal import STL
    except ImportError:
        return detect_ewma(values, calibration, config)

    period = _infer_period(calibration)
    if period is None or period >= max(len(calibration) - 1, 8):
        return detect_ewma(values, calibration, config)

    try:
        stl = STL(calibration, period=period, robust=True)
        res_cal = stl.fit()
        seasonal_profile = res_cal.seasonal[:period]
        seasonal_vals = np.tile(seasonal_profile, len(values) // period + 1)[: len(values)]
        sigma = res_cal.resid.std(ddof=0)
        if sigma < 1e-9:
            return _empty(len(values))
        # baseline = EWMA(trend part) + seasonal（基线应该"跟着周期性走"）
        trend_vals = values - seasonal_vals
        ewma_trend = _ewma(trend_vals, alpha=config.alpha)
        baseline = ewma_trend + seasonal_vals
        return np.abs(values - baseline) > config.k * sigma
    except Exception:
        return detect_ewma(values, calibration, config)


def _infer_period(values: np.ndarray, max_period: int = 48) -> int | None:
    """从校准段的自相关推断主要周期长度。

    对运维指标：采样频率已知的话可以直接传（每 5min 一个点 → 日周期 = 288），
    但这里做通用 fallback：找自相关第一个显著峰值。
    """
    if len(values) < 32:
        return None
    centered = values - values.mean()
    acf = np.correlate(centered, centered, mode="full")[len(centered) - 1 :]
    acf = acf / (acf[0] + 1e-9)
    # 跳过 lag=0，找 lag=1 ~ max_period 内第一个局部峰值
    for lag in range(2, min(max_period, len(acf) - 1)):
        if acf[lag] > acf[lag - 1] and acf[lag] > acf[lag + 1] and acf[lag] > 0.25:
            return lag
    return None


def _ewma(values: np.ndarray, alpha: float = 0.3) -> np.ndarray:
    """纯 numpy EWMA（无 torch 依赖）。"""
    out = np.zeros_like(values)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def detect_all(
    values: np.ndarray, calibration: np.ndarray, config: DetectorConfig | None = None
) -> dict[str, np.ndarray]:
    """跑全部检测器，返回 {名称: 布尔数组}。"""
    config = config or DetectorConfig()
    values = np.asarray(values, dtype=float)
    calibration = np.asarray(calibration, dtype=float)
    return {
        "three_sigma": detect_three_sigma(values, calibration, config),
        "mad": detect_mad(values, calibration, config),
        "rolling_z": detect_rolling_z(values, config),
        "rolling_mad": detect_rolling_mad(values, config),
        "ewma": detect_ewma(values, calibration, config),
        "isolation_forest": detect_isolation_forest(values, calibration, config),
        # P1-4 自适应阈值
        "adaptive_threshold": detect_adaptive_threshold(values, calibration, config),
        "seasonal_ewma": detect_seasonal_ewma(values, calibration, config),
    }


def binary_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """二分类指标；分母为 0 时返回 0，避免用 nan 假装有结论。"""
    y_true = np.asarray(y_true, dtype=bool)
    y_pred = np.asarray(y_pred, dtype=bool)
    tp = int(np.sum(y_true & y_pred))
    fp = int(np.sum(~y_true & y_pred))
    fn = int(np.sum(y_true & ~y_pred))
    tn = int(np.sum(~y_true & ~y_pred))

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "fp_rate": fp / (fp + tn) if fp + tn else 0.0,
    }


def inject_anomalies(
    values: np.ndarray,
    labels: np.ndarray,
    count: int,
    calibration_std: float,
    *,
    seed: int = 17,
    magnitude: float = 6.0,
) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """在序列后半段注入确定性的尖峰/凹陷/电平漂移，返回新序列、新标签、注入位置。

    注入点之间至少间隔 5 个点，且避开已标注正例，避免两个异常互相掩盖。
    """
    values = np.asarray(values, dtype=float).copy()
    labels = np.asarray(labels, dtype=bool).copy()
    start = len(values) // 2
    if magnitude <= 0 or calibration_std <= 0 or count <= 0:
        return values, labels, []

    candidates = [
        index
        for index in range(start + 1, len(values) - 4)
        if not labels[max(0, index - 2) : index + 6].any()
    ]
    if not candidates:
        return values, labels, []

    rng = np.random.default_rng(seed)
    picked = sorted(rng.choice(candidates, size=min(count, len(candidates)), replace=False).tolist())
    injected: list[int] = []
    last = -10
    for order, index in enumerate(picked):
        if index - last < 5:
            continue
        offset = magnitude * calibration_std
        kind = order % 3
        if kind == 0:
            values[index] += offset
            labels[index] = True
            injected.append(index)
        elif kind == 1:
            values[index] -= offset
            labels[index] = True
            injected.append(index)
        else:
            span = values[index : index + 3]
            values[index : index + 3] = span + 0.7 * offset
            labels[index : index + 3] = True
            injected.extend(range(index, index + 3))
        last = index
    return values, labels, injected


# ---------------------------------------------------------------------------
# 容量预测基线
# ---------------------------------------------------------------------------


def forecast_last(train: np.ndarray, horizon: int) -> np.ndarray:
    """用训练段最后一个值填平 horizon 步。"""
    return np.full(horizon, float(train[-1]))


def forecast_moving_avg(train: np.ndarray, horizon: int, window: int = 8) -> np.ndarray:
    """训练段最后 window 点的均值填平 horizon 步。"""
    use = min(window, len(train))
    return np.full(horizon, float(train[-use:].mean()))


def forecast_ewma(train: np.ndarray, horizon: int, alpha: float = 0.3) -> np.ndarray:
    """把训练段最后一个 EWMA 水平外推 horizon 步。"""
    level = float(train[0])
    for value in train[1:]:
        level = alpha * value + (1 - alpha) * level
    return np.full(horizon, level)


def forecast_linear(train: np.ndarray, horizon: int) -> np.ndarray:
    """用最近 12 点的线性趋势外推 horizon 步；避免除零。"""
    window = min(12, len(train))
    x = np.arange(window, dtype=float)
    y = train[-window:]
    x_mean = x.mean()
    denom = np.sum((x - x_mean) ** 2)
    if denom == 0:
        return forecast_last(train, horizon)
    slope = np.sum((x - x_mean) * (y - y.mean())) / denom
    intercept = y.mean() - slope * x_mean
    future_x = np.arange(window, window + horizon, dtype=float)
    return intercept + slope * future_x


def forecast_quantile_peak(
    train: np.ndarray, horizon: int, q: float = 0.95
) -> np.ndarray:
    """容量峰值预测：训练段 q 分位数填平 horizon 步，直接给出可承载上限。"""
    return np.full(horizon, float(np.quantile(train, q)))


def forecast_all(
    train: np.ndarray,
    horizon: int,
    *,
    moving_avg_window: int = 8,
    ewma_alpha: float = 0.3,
    linear_window: int = 12,
    quantile: float = 0.95,
) -> dict[str, np.ndarray]:
    """返回 {名称: 长度 horizon 的预测数组}。"""
    train = np.asarray(train, dtype=float)
    return {
        "last": forecast_last(train, horizon),
        "moving_avg": forecast_moving_avg(train, horizon, moving_avg_window),
        "ewma": forecast_ewma(train, horizon, ewma_alpha),
        "linear": forecast_linear(train, horizon),
        f"peak_p{int(quantile * 100):02d}": forecast_quantile_peak(train, horizon, quantile),
    }


def forecast_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    """预测指标：MAE、RMSE、MAPE（若分母非零）、Bias、MASE 分子。"""
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    errors = predicted - actual
    abs_errors = np.abs(errors)

    mae = float(abs_errors.mean())
    rmse = float(np.sqrt((errors ** 2).mean()))
    denominator = np.where(np.abs(actual) < 1e-9, 1e-9, actual)
    mape = float(np.mean(np.abs(errors / denominator)) * 100)
    bias = float(errors.mean())
    return {"mae": mae, "rmse": rmse, "mape_pct": mape, "bias": bias}


def walk_forward_forecast(
    values: np.ndarray,
    *,
    horizon: int,
    step: int = 1,
    train_min: int = 20,
    **forecast_kwargs,
) -> dict[str, list[float]]:
    """滚动扩展窗口验证：每次把训练段扩 1 点，预测接下来 ``horizon`` 点。"""
    values = np.asarray(values, dtype=float)
    results: dict[str, list[float]] = {"actual": [], "step_index": []}
    start = train_min
    if start + horizon >= len(values):
        return results
    for cursor in range(start, len(values) - horizon + 1, step):
        train = values[:cursor]
        actual = values[cursor : cursor + horizon]
        results["actual"].append(float(actual[0]))
        results["step_index"].append(cursor)
        for name, predicted in forecast_all(train, horizon, **forecast_kwargs).items():
            bucket = results.setdefault(f"{name}_pred", [])
            bucket.append(float(predicted[0]))
    return results

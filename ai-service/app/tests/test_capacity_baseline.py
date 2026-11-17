"""容量预测模块的单元测试：锁住因果性、常量安全、外推形状。"""

import numpy as np

from app.training.anomaly import (
    forecast_all,
    forecast_ewma,
    forecast_last,
    forecast_linear,
    forecast_metrics,
    forecast_moving_avg,
    forecast_quantile_peak,
    walk_forward_forecast,
)


def _rw(size=60, seed=7):
    """简单带漂移的随机游走，确保趋势模型有东西抓。"""
    rng = np.random.default_rng(seed)
    base = np.cumsum(rng.normal(0, 0.5, size)) + 50
    base[:20] = 50
    return base


def test_forecast_last_repeats_final_value():
    values = np.array([1, 2, 3, 4, 5.0])
    horizon = 4
    predicted = forecast_last(values, horizon)
    assert len(predicted) == horizon
    assert np.all(predicted == 5.0)


def test_moving_avg_uses_last_window():
    values = np.arange(20, dtype=float)
    horizon = 3
    predicted = forecast_moving_avg(values, horizon, window=4)
    expected = float(np.mean(values[-4:]))
    assert np.allclose(predicted, expected)


def test_ewma_converges_to_level():
    values = np.array([40.0] * 5 + [60.0] * 10)
    predicted = forecast_ewma(values, 3, alpha=0.5)
    # alpha=0.5 时最后一个点水平应非常接近 60
    assert np.allclose(predicted, predicted[0])
    assert predicted[0] > 59.0  # 几乎收敛到 60


def test_linear_extrapolation_handles_flat_window():
    flat = np.full(10, 42.0)
    predicted = forecast_linear(flat, 5)
    assert np.allclose(predicted, 42.0)


def test_linear_extrapolation_slope_shape():
    # 明确的上升趋势
    values = np.arange(20, dtype=float)
    predicted = forecast_linear(values, 3)
    assert predicted[0] < predicted[1] < predicted[2]


def test_quantile_peak_uses_requested_quantile():
    values = np.arange(100, dtype=float)  # 0..99
    assert forecast_quantile_peak(values, 3, q=0.95)[0] == np.quantile(values, 0.95)
    assert forecast_quantile_peak(values, 3, q=0.50)[0] == 49.5


def test_forecast_all_return_names_and_length():
    train = _rw(60)
    horizon = 3
    results = forecast_all(train, horizon)
    assert set(results.keys()) >= {"last", "moving_avg", "ewma", "linear"}
    for name, predicted in results.items():
        assert len(predicted) == horizon, name


def test_metrics_computation_handles_zero_denominator():
    actual = np.zeros(10, dtype=float)
    predicted = np.full(10, 1.0)
    metrics = forecast_metrics(actual, predicted)
    assert metrics["mae"] == 1.0
    assert metrics["rmse"] == 1.0
    assert metrics["bias"] == 1.0


def test_metrics_are_perfect_for_identical_values():
    actual = np.array([1.0, 2.0, 3.0])
    metrics = forecast_metrics(actual, actual)
    assert metrics["mae"] == 0.0
    assert metrics["rmse"] == 0.0
    assert metrics["bias"] == 0.0


def test_walk_forward_returns_samples_only_when_enough_points():
    short = _rw(25)
    # train_min=30 导致根本不滚动
    result = walk_forward_forecast(short, horizon=1, train_min=30)
    assert not result["actual"]

    result = walk_forward_forecast(short, horizon=1, train_min=10)
    assert len(result["actual"]) == len(result["step_index"])
    assert result["step_index"][0] == 10


def test_walk_forward_matches_direct_call_first_point():
    values = _rw(80)
    result = walk_forward_forecast(values, horizon=3, train_min=20, step=1)
    direct = forecast_last(values[:20], 3)[0]
    assert result["actual"][0] == values[20]
    assert result["last_pred"][0] == direct

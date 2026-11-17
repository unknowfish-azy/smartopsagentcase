"""D3 异常检测模块的单元测试：只锁行为，不锁具体 F1（数据太小，F1 易漂）。"""

import numpy as np

from app.training.anomaly import (
    DetectorConfig,
    binary_metrics,
    detect_all,
    inject_anomalies,
)


def _series(size=120, seed=7):
    rng = np.random.default_rng(seed)
    return 50 + rng.normal(0, 1.0, size)


def test_blatant_spike_is_caught_by_magnitude_detectors():
    values = _series()
    values[80] = values.mean() + 10 * values.std()
    calibration = values[:60]

    predictions = detect_all(values, calibration, DetectorConfig())

    for name in ("three_sigma", "mad", "rolling_mad", "ewma", "rolling_z"):
        assert predictions[name][80], f"{name} 漏掉了 10σ 尖峰"


def test_zero_variance_calibration_does_not_alarm():
    values = np.full(60, 40.0)
    values[-1] = 41.0
    predictions = detect_all(values, values[:30], DetectorConfig())

    for name in ("three_sigma", "mad", "ewma"):
        assert not predictions[name].any(), f"{name} 在常量序列上产生告警"


def test_binary_metrics_basic_math():
    perfect = binary_metrics(np.array([True, False, True]), np.array([True, False, True]))
    assert perfect["f1"] == 1.0
    assert perfect["fp_rate"] == 0.0

    missed = binary_metrics(np.array([True, True, False]), np.zeros(3, dtype=bool))
    assert missed["recall"] == 0.0
    assert missed["f1"] == 0.0
    assert missed["fp_rate"] == 0.0

    noisy = binary_metrics(np.array([True, False, False, False]), np.array([True, True, False, False]))
    assert noisy["tp"] == 1 and noisy["fp"] == 1
    assert noisy["fp_rate"] == 1 / 3


def test_inject_anomalies_is_deterministic_and_marks_labels():
    values = _series(size=100)
    labels = np.zeros(100, dtype=bool)

    first_values, first_labels, first_positions = inject_anomalies(
        values, labels, 6, calibration_std=1.0, seed=17
    )
    second_values, second_labels, second_positions = inject_anomalies(
        values, labels, 6, calibration_std=1.0, seed=17
    )

    assert first_positions == second_positions
    assert np.array_equal(first_values, second_values)
    assert np.array_equal(first_labels, second_labels)
    assert set(first_positions) == set(np.flatnonzero(first_labels))
    assert first_positions and min(first_positions) >= len(values) // 2

    # 原序列不被就地修改
    assert not np.array_equal(first_values, values)


def test_inject_anomalies_skips_region_near_existing_labels():
    values = _series(size=100)
    labels = np.zeros(100, dtype=bool)
    labels[90:95] = True

    _, injected_labels, positions = inject_anomalies(
        values, labels, 8, calibration_std=1.0, seed=17
    )

    assert positions
    for position in positions:
        assert not labels[max(0, position - 2) : position + 6].any()
    assert injected_labels[90:95].all()

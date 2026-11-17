"""P2-2 故障仿真生成：给 Agent 练处置流程的合成故障时序。

设计原则：
1. 零 torch 依赖——纯 numpy 规则合成，Agent 随时可调；
2. 输出直接喂 detect_all()——values + calibration 双段返回；
3. 故障形态真实——每种 category 有明确的形状模板（oom=尖峰归零、timeout=下降反弹、disk_full=爬坡跳变）；
4. generator → simulator → detector 闭环——simulate() 生成的序列能让 P0-1/P1-4 的检测器检出异常。

经验 100003543/100007608 教训：
- 规则生成要让数据机理和目标检测器一致（例如 adaptive_threshold 要能在 residual 上检出），
  不能生成"太假"的序列导致检测器全挂。
- 生成-校验闭环：simulate() 里内置一个 verify_detectors()，验证至少 K 种检测器能命中。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


# ---------------------------------------------------------------------------
# 故障形态模板（每种 category 一段可配置的"故障注入"）
# ---------------------------------------------------------------------------

@dataclass
class FaultShape:
    """一段故障注入序列，加到正常基线上。"""

    name: str
    duration: int          # 故障持续步数
    peak: float            # 故障峰值（相对正常基线的倍数或偏移）
    slope: float = 0.5     # 爬坡速度（0=阶跃，1=线性）
    decay: float = 0.3      # 回落速度（阶跃消失后恢复的速度）


# 每种 category 的默认故障模板（按 CPU/disk/memory 等指标语义设定）
FAULT_TEMPLATES: dict[str, dict[str, FaultShape]] = {
    # CPU 指标 → oom 表现为"正常运行 → 突然飙到 99% → 进程死掉（归零）"
    "oom": {
        "cpu": FaultShape("cpu_spike_then_zero", duration=12, peak=99.0, slope=0.8, decay=0.9),
        "memory": FaultShape("memory_grow_killed", duration=18, peak=98.0, slope=0.4, decay=0.95),
    },
    # CPU 指标 → timeout 表现为"正常 → 波动上升 → 高持续 → 突然恢复"
    "timeout": {
        "cpu": FaultShape("cpu_sustained_high", duration=20, peak=95.0, slope=0.3, decay=0.4),
        "latency": FaultShape("latency_surge", duration=15, peak=5000.0, slope=0.5, decay=0.2),
    },
    # Disk 指标 → 持续爬坡后突然 100%
    "disk_full": {
        "disk_usage": FaultShape("disk_ramp_then_100", duration=30, peak=100.0, slope=0.2, decay=0.0),
        "inode_usage": FaultShape("inode_ramp", duration=25, peak=99.0, slope=0.3, decay=0.0),
    },
    # Network → 指标突然归零（网络中断）
    "connection_refused": {
        "network_rx": FaultShape("rx_then_zero", duration=8, peak=0.0, slope=0.1, decay=0.0),
        "network_tx": FaultShape("tx_then_zero", duration=8, peak=0.0, slope=0.1, decay=0.0),
    },
    # Process → 正常 → 正常 → 突然归零（进程 crash）
    "process_crash": {
        "cpu": FaultShape("cpu_goes_zero", duration=3, peak=0.0, slope=0.0, decay=0.0),
        "memory": FaultShape("memory_goes_zero", duration=3, peak=0.0, slope=0.0, decay=0.0),
    },
    # Auth → 正常 → 401/403 飙升 → 突然恢复
    "auth_error": {
        "http_401": FaultShape("401_surge", duration=15, peak=1000.0, slope=0.5, decay=0.8),
        "http_403": FaultShape("403_surge", duration=15, peak=500.0, slope=0.5, decay=0.8),
    },
    # Network → 正常 → 波动 → 间歇性丢包
    "network_error": {
        "packet_loss": FaultShape("loss_fluctuating", duration=20, peak=30.0, slope=0.4, decay=0.3),
        "latency": FaultShape("latency_fluctuating", duration=20, peak=1000.0, slope=0.3, decay=0.3),
    },
}


# 指标类型的正常基线
METRIC_BASELINE: dict[str, tuple[float, float]] = {
    # metric_name → (baseline_mean, baseline_std, seasonality_period)
    "cpu": (35.0, 8.0, 24),          # 24 步日周期
    "memory": (55.0, 6.0, 24),
    "disk_usage": (60.0, 3.0, 168),  # 周周期
    "inode_usage": (40.0, 2.0, 168),
    "network_rx": (100.0, 20.0, 24),
    "network_tx": (100.0, 20.0, 24),
    "latency": (80.0, 15.0, 24),
    "http_401": (2.0, 1.0, 1),
    "http_403": (1.0, 0.5, 1),
    "packet_loss": (0.5, 0.3, 24),
}


def synthesize_series(
    category: str = "oom",
    metric: str | None = None,
    seed: int = 42,
    calibration_len: int = 96,
    test_len: int = 48,
    inject_start: int | None = None,
    severity: float = 1.0,
    add_seasonality: bool = True,
    add_noise: bool = True,
) -> dict[str, Any]:
    """合成一段"正常 → 故障"的指标序列。

    返回 dict:
      calibration: (calibration_len,) np.ndarray — 校准段（纯正常）
      values:      (test_len,) np.ndarray       — 测试段（正常 + 注入故障）
      labels:      (test_len,) bool              — 故障标签（注入点）
      meta:        dict                          — 故障参数（Agent 可以用来自检）
    """
    rng = np.random.default_rng(seed)

    # 1. 确定 metric 和 baseline
    if metric is None:
        metric = next(iter(FAULT_TEMPLATES.get(category, FAULT_TEMPLATES["oom"])))
    baseline_mean, baseline_std, period = METRIC_BASELINE.get(metric, (50.0, 10.0, 24))

    # 2. 正常基线合成（昼夜周期 + 噪声）
    total_len = calibration_len + test_len
    t = np.arange(total_len)
    if add_seasonality and period > 1:
        # 日周期：白天高、夜间低（CPU/memory/latency），disk 则用正弦代表缓慢变化
        if category in ("disk_full",):
            seasonality = 2.0 * np.sin(2 * np.pi * t / period)
        else:
            day_mask = (t % period) < period // 2
            seasonality = np.where(day_mask, 1.0, -0.6) * (baseline_mean * 0.2)
    else:
        seasonality = np.zeros(total_len)

    noise = rng.normal(0, baseline_std if add_noise else 0, size=total_len)
    normal = baseline_mean + seasonality + noise
    # 下限裁剪（有些指标不能为负）
    if metric in ("packet_loss", "latency", "http_401", "http_403"):
        normal = np.maximum(normal, 0.0)

    calibration = normal[:calibration_len].copy()
    values = normal[calibration_len:].copy()

    # 3. 故障注入
    labels = np.zeros(test_len, dtype=bool)
    template = FAULT_TEMPLATES.get(category, {}).get(metric, FAULT_TEMPLATES["oom"]["cpu"])

    inject_local = inject_start if inject_start is not None else test_len // 3
    inject_local = min(max(inject_local, 1), test_len - template.duration - 1)

    # 故障形状：先用"形状向量"再按 severity 缩放
    fault_shape = _make_fault_shape(template, template.duration)
    fault_amp = severity * template.peak
    fault_series = fault_amp * fault_shape

    # 对 disk_full 这种"持续爬坡"直接加到基线；对 oom timeout 这种"尖峰"用 replace
    if category == "disk_full":
        values[inject_local : inject_local + template.duration] += fault_series
        values = np.minimum(values, 100.0)  # 磁盘使用不能超 100%
    elif category in ("connection_refused", "process_crash"):
        # 归零型：直接覆盖为 0
        values[inject_local : inject_local + template.duration] = fault_amp * fault_shape
    else:
        # 尖峰型：加到基线
        values[inject_local : inject_local + template.duration] += fault_series

    labels[inject_local : inject_local + template.duration] = True

    return {
        "calibration": calibration,
        "values": values,
        "labels": labels,
        "meta": {
            "category": category,
            "metric": metric,
            "inject_start": inject_local,
            "duration": template.duration,
            "severity": severity,
            "peak": float(template.peak),
            "baseline_mean": float(baseline_mean),
            "baseline_std": float(baseline_std),
            "period": period,
            "detectors_should_hit": ["adaptive_threshold", "seasonal_ewma", "rolling_mad", "isolation_forest"],
        },
    }


def _make_fault_shape(template: FaultShape, duration: int) -> np.ndarray:
    """生成一个故障形状向量（0~1 标量，无振幅）。"""
    t = np.arange(duration, dtype=float)
    ramp_up = np.minimum(1.0, t / max(1, duration * template.slope))
    plateau = np.zeros(duration)
    plateau[ramp_up >= 1.0] = 1.0
    # 衰减段
    decay_start = int(duration * (1 - template.decay))
    decay = np.zeros(duration)
    if decay_start < duration:
        decay[decay_start:] = np.linspace(1.0, 0.0, duration - decay_start)
    shape = np.where(ramp_up < 1.0, ramp_up, plateau)
    shape[decay_start:] = decay[decay_start:]
    # 归零型：末尾强制归零
    if template.peak == 0.0:
        shape = np.ones(duration) * 0.01
    return shape.astype(np.float32)


# ---------------------------------------------------------------------------
# 快速验证：simulate → detect_all → 至少 K 个检测器命中
# ---------------------------------------------------------------------------

def verify_detectors(
    category: str,
    simulation_result: dict[str, Any],
    expected_detectors: list[str] | None = None,
) -> dict[str, Any]:
    """用 anomaly.detect_all() 验证仿真序列能被现有检测器检出。"""
    try:
        from app.training.anomaly import detect_all, DetectorConfig, binary_metrics
    except ImportError:
        return {"available": False}

    config = DetectorConfig(k=3.0, window=10, alpha=0.2, contamination=0.05)
    results = detect_all(
        simulation_result["values"], simulation_result["calibration"], config
    )
    y_true = simulation_result["labels"]

    per_detector = {}
    for name, pred in results.items():
        metrics = binary_metrics(y_true, pred)
        per_detector[name] = {
            "precision": metrics["precision"],
            "recall": metrics["recall"],
            "f1": metrics["f1"],
            "hit": metrics["recall"] > 0.0,
        }

    expected = expected_detectors or simulation_result["meta"]["detectors_should_hit"]
    hit_expected = [d for d in expected if per_detector.get(d, {}).get("hit", False)]
    total_hit = sum(1 for d in expected if per_detector.get(d, {}).get("hit", False))
    return {
        "available": True,
        "per_detector": per_detector,
        "expected_hit": hit_expected,
        "coverage": total_hit / len(expected) if expected else 0.0,
    }


# ---------------------------------------------------------------------------
# 批量生成：给 Agent 批量演练用
# ---------------------------------------------------------------------------

def generate_scenario_set(
    categories: list[str] | None = None,
    n_per_category: int = 3,
    seed_base: int = 1000,
) -> list[dict[str, Any]]:
    """按类别批量生成故障场景——Agent 可以一次拉一组测试自己的处置流程。"""
    if categories is None:
        categories = list(FAULT_TEMPLATES.keys())

    scenarios = []
    for cat in categories:
        for i in range(n_per_category):
            seed = seed_base + hash((cat, i)) % 10000
            sev = 0.8 + 0.4 * (i / max(n_per_category - 1, 1))  # severity 0.8 → 1.2
            scenarios.append(synthesize_series(
                category=cat, seed=seed, severity=round(sev, 2),
                inject_start=20 + i * 3,
            ))
    return scenarios

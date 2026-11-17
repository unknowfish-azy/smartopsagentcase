"""P2-2 故障仿真生成推理服务。

纯 numpy 规则实现，无 torch 依赖，永远 available。
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..training.simulator import (
    FAULT_TEMPLATES,
    synthesize_series,
    verify_detectors,
)


def get_model_info() -> dict[str, Any]:
    """返回模拟器元信息：支持的类别、每个类别可用指标。"""
    metrics_per_category = {cat: list(tpl.keys()) for cat, tpl in FAULT_TEMPLATES.items()}
    return {
        "available": True,
        "kind": "rule_based",
        "reason": "纯 numpy 规则生成，零依赖",
        "categories": list(FAULT_TEMPLATES.keys()),
        "metrics_per_category": metrics_per_category,
    }


def simulate(request) -> dict[str, Any]:
    """按请求生成合成故障时序 + 可选检测器验证。"""
    result = synthesize_series(
        category=request.category,
        metric=request.metric,
        seed=request.seed,
        calibration_len=request.calibration_len,
        test_len=request.test_len,
        inject_start=request.inject_start,
        severity=request.severity,
        add_seasonality=request.add_seasonality,
        add_noise=request.add_noise,
    )

    # 检测器验证
    if request.verify:
        dv = verify_detectors(request.category, result)
    else:
        dv = {"available": False}

    # numpy → list（pydantic 序列化）
    calib = np.asarray(result["calibration"]).astype(float).tolist()
    values = np.asarray(result["values"]).astype(float).tolist()
    labels = np.asarray(result["labels"]).astype(bool).tolist()

    return {
        "ok": True,
        "mode": "rule_based",
        "category": request.category,
        "metric": result["meta"]["metric"],
        "calibration": calib,
        "values": values,
        "labels": labels,
        "meta": result["meta"],
        "detector_verification": dv,
    }

"""P1-3 时序异常语义化服务。

把 AnomalyTransformer / IsolationForest 输出的"异常分数"转化为
"异常分 + 语义描述"双结果，让 Kimi 无需解读原始曲线即可获得诊断结论。

设计原则：
- 统计特征用确定性算法提取（突升/突降/抖动/周期/阶梯），不依赖 LLM；
- 语义描述优先用模板拼装（永远可用），LLM 仅用于润色；
- LLM 不可用时返回模板描述，不会失败；
- 不伪造：描述只反映统计事实，不做未经验证的根因推断。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

from .llm import LLMService


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

PatternType = Literal[
    "sudden_spike",      # 突升
    "sudden_drop",       # 突降
    "step_increase",     # 阶梯式上升
    "step_decrease",     # 阶梯式下降
    "oscillation",       # 抖动
    "periodic",          # 周期性
    "gradual_drift",     # 缓慢漂移
    "flat",              # 平稳（无异常模式）
    "unknown",           # 未识别
]


@dataclass
class TemporalPattern:
    """时序异常的统计模式特征。"""
    pattern: PatternType
    # 异常起止位置（索引）
    start_idx: int
    end_idx: int
    # 异常幅度（相对基线的倍数）
    magnitude: float
    # 基线均值 / 标准差
    baseline_mean: float
    baseline_std: float
    # 异常段均值 / 标准差
    anomaly_mean: float
    anomaly_std: float
    # 抖动强度（异常段 std / 基线 std）
    volatility: float
    # 是否检测到周期性（FFT 主峰显著）
    has_periodicity: bool
    # 主周期长度（样本点数），无周期时为 0
    period_len: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "start_idx": self.start_idx,
            "end_idx": self.end_idx,
            "magnitude": round(self.magnitude, 3),
            "baseline_mean": round(self.baseline_mean, 3),
            "baseline_std": round(self.baseline_std, 3),
            "anomaly_mean": round(self.anomaly_mean, 3),
            "anomaly_std": round(self.anomaly_std, 3),
            "volatility": round(self.volatility, 3),
            "has_periodicity": self.has_periodicity,
            "period_len": self.period_len,
        }


# ---------------------------------------------------------------------------
# 统计模式识别（确定性算法，永远可用）
# ---------------------------------------------------------------------------

def detect_pattern(
    series: np.ndarray,
    anomaly_scores: np.ndarray,
    threshold: float = 0.5,
) -> TemporalPattern:
    """从时序数据 + 异常分中识别异常模式。

    Args:
        series: 原始指标值，shape (T,)
        anomaly_scores: 异常分数，shape (T,)，值域 [0, 1]
        threshold: 异常分阈值，高于此值视为异常点
    """
    series = np.asarray(series, dtype=np.float64)
    scores = np.asarray(anomaly_scores, dtype=np.float64)

    anomaly_mask = scores >= threshold
    if not anomaly_mask.any():
        return _flat_pattern(series)

    indices = np.where(anomaly_mask)[0]
    start_idx, end_idx = int(indices[0]), int(indices[-1])

    baseline = series[~anomaly_mask] if (~anomaly_mask).sum() > 0 else series
    anomaly_seg = series[anomaly_mask]

    baseline_mean = float(baseline.mean())
    baseline_std = float(baseline.std()) + 1e-8
    anomaly_mean = float(anomaly_seg.mean())
    anomaly_std = float(anomaly_seg.std())

    magnitude = (anomaly_mean - baseline_mean) / (abs(baseline_mean) + 1e-8)
    volatility = anomaly_std / baseline_std

    has_period, period_len = _detect_periodicity(series)

    pattern = _classify_pattern(
        series, anomaly_mask, baseline_mean, baseline_std,
        anomaly_mean, magnitude, volatility,
    )

    return TemporalPattern(
        pattern=pattern,
        start_idx=start_idx,
        end_idx=end_idx,
        magnitude=abs(magnitude),
        baseline_mean=baseline_mean,
        baseline_std=baseline_std,
        anomaly_mean=anomaly_mean,
        anomaly_std=anomaly_std,
        volatility=volatility,
        has_periodicity=has_period,
        period_len=period_len,
    )


def _flat_pattern(series: np.ndarray) -> TemporalPattern:
    mean = float(series.mean())
    std = float(series.std())
    return TemporalPattern(
        pattern="flat", start_idx=-1, end_idx=-1,
        magnitude=0.0, baseline_mean=mean, baseline_std=std,
        anomaly_mean=mean, anomaly_std=std, volatility=1.0,
        has_periodicity=False, period_len=0,
    )


def _classify_pattern(
    series: np.ndarray,
    mask: np.ndarray,
    base_mean: float,
    base_std: float,
    anom_mean: float,
    magnitude: float,
    volatility: float,
) -> PatternType:
    # 抖动：异常段 std 远大于基线 std
    if volatility > 3.0:
        return "oscillation"

    seg = series[mask]
    seg_ratio = len(seg) / len(series)

    # 突升 / 突降：异常段短（<15% 时长）+ 均值偏移大 → 尖刺型
    if seg_ratio < 0.15 and abs(magnitude) > 0.5:
        return "sudden_spike" if magnitude > 0 else "sudden_drop"

    # 阶梯：异常段长 + 均值偏移大 + 异常段 std 小 → 持续偏移
    if abs(magnitude) > 0.5 and volatility < 1.5:
        # 检查是否阶梯（异常段内部仍有均值台阶）
        if len(seg) >= 4:
            half = len(seg) // 2
            first_half = seg[:half].mean()
            second_half = seg[half:].mean()
            if abs(second_half - first_half) > base_std * 2:
                return "step_increase" if second_half > first_half else "step_decrease"
        return "step_increase" if magnitude > 0 else "step_decrease"

    # 突升 / 突降：均值偏移大
    if magnitude > 0.3:
        return "sudden_spike"
    if magnitude < -0.3:
        return "sudden_drop"

    # 缓慢漂移：异常段均值偏移小但持续
    if 0.1 < abs(magnitude) <= 0.3:
        return "gradual_drift"

    return "unknown"


def _detect_periodicity(series: np.ndarray) -> tuple[bool, int]:
    """用 FFT 检测周期性。返回 (是否有周期, 主周期长度)。"""
    if len(series) < 16:
        return False, 0
    centered = series - series.mean()
    fft = np.fft.rfft(centered)
    power = np.abs(fft) ** 2
    freqs = np.fft.rfftfreq(len(series))
    # 跳过直流分量
    if len(power) < 2:
        return False, 0
    power[0] = 0
    peak_idx = int(power.argmax())
    if power[peak_idx] < power.sum() * 0.3:
        return False, 0
    if freqs[peak_idx] <= 0:
        return False, 0
    period = int(round(1.0 / freqs[peak_idx]))
    return (period >= 4), period


# ---------------------------------------------------------------------------
# 模板化语义描述（永远可用）
# ---------------------------------------------------------------------------

_PATTERN_TEMPLATES: dict[PatternType, str] = {
    "sudden_spike": "指标出现突然上升，幅度 {magnitude:.1%}，异常段均值 {anom_mean:.2f}（基线 {base_mean:.2f}）",
    "sudden_drop": "指标出现突然下降，幅度 {magnitude:.1%}，异常段均值 {anom_mean:.2f}（基线 {base_mean:.2f}）",
    "step_increase": "指标呈阶梯式上升，异常段均值 {anom_mean:.2f}（基线 {base_mean:.2f}），可能是容量/资源类故障前兆",
    "step_decrease": "指标呈阶梯式下降，异常段均值 {anom_mean:.2f}（基线 {base_mean:.2f}），可能是流量流失或下游故障",
    "oscillation": "指标出现明显抖动，异常段标准差为基线的 {volatility:.1f} 倍，符合缓存雪崩或重试风暴特征",
    "periodic": "指标呈周期性波动，主周期约 {period} 个采样点",
    "gradual_drift": "指标缓慢漂移，幅度 {magnitude:.1%}，可能是内存泄漏或缓慢堆积类问题",
    "flat": "指标运行平稳，未识别到异常模式",
    "unknown": "指标存在异常但模式未明确，异常段均值 {anom_mean:.2f}（基线 {base_mean:.2f}）",
}


def render_template_description(pattern: TemporalPattern) -> str:
    """用模板拼装描述，不依赖 LLM。"""
    template = _PATTERN_TEMPLATES.get(pattern.pattern, _PATTERN_TEMPLATES["unknown"])
    return template.format(
        magnitude=pattern.magnitude,
        anom_mean=pattern.anomaly_mean,
        base_mean=pattern.baseline_mean,
        volatility=pattern.volatility,
        period=pattern.period_len,
    )


# ---------------------------------------------------------------------------
# LLM 润色（可选增强）
# ---------------------------------------------------------------------------

_NARRATOR_PROMPT = """你是运维诊断专家。基于以下统计特征，给出一句简洁的异常模式描述（不超过 80 字）。

指标名称：{metric_name}
异常模式：{pattern}
异常幅度：{magnitude:.1%}
基线均值：{base_mean:.2f}
异常段均值：{anom_mean:.2f}
抖动强度：{volatility:.2f}
{periodicity_line}

只输出描述文本，不要任何前缀。"""


async def narrate(
    metric_name: str,
    series: np.ndarray,
    anomaly_scores: np.ndarray,
    llm: LLMService | None = None,
) -> dict[str, Any]:
    """生成"异常分 + 语义描述"双结果。

    Args:
        metric_name: 指标名（如 "cpu_usage"）
        series: 时序数据
        anomaly_scores: 异常分数（来自 anomaly_detector）
        llm: 可选 LLM 服务；为 None 时只用模板描述

    Returns:
        {
            "pattern": TemporalPattern.to_dict(),
            "description": str,          # 最终描述（LLM 润色或模板）
            "template_description": str, # 模板描述（永远存在）
            "llm_enhanced": bool,        # 是否经 LLM 润色
        }
    """
    pattern = detect_pattern(series, anomaly_scores)
    template_desc = render_template_description(pattern)

    description = template_desc
    llm_enhanced = False

    if llm is not None and pattern.pattern not in ("flat", "unknown"):
        periodicity_line = (
            f"主周期：{pattern.period_len} 个采样点"
            if pattern.has_periodicity else "无明显周期"
        )
        prompt = _NARRATOR_PROMPT.format(
            metric_name=metric_name,
            pattern=pattern.pattern,
            magnitude=pattern.magnitude,
            base_mean=pattern.baseline_mean,
            anom_mean=pattern.anomaly_mean,
            volatility=pattern.volatility,
            periodicity_line=periodicity_line,
        )
        try:
            llm_text = await llm.generate(
                prompt,
                system_prompt="你是运维诊断专家，只做简洁描述。",
            )
            llm_text = llm_text.strip()
            if llm_text and len(llm_text) <= 200:
                description = llm_text
                llm_enhanced = True
        except Exception:
            pass  # LLM 失败时保留模板描述

    return {
        "pattern": pattern.to_dict(),
        "description": description,
        "template_description": template_desc,
        "llm_enhanced": llm_enhanced,
    }


def get_model_info() -> dict[str, Any]:
    return {
        "available": True,
        "kind": "statistical_plus_llm",
        "reason": "统计模式识别永远可用，LLM 润色可选",
        "supported_patterns": list(_PATTERN_TEMPLATES.keys()),
    }

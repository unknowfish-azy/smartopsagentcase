# -*- coding: utf-8 -*-
"""P2-7 / C：因果图 / 反事实（**仅骨架**）。

⚠️ **当前状态（2026-11-24，骨架）**：本包提供**数据契约**、**评测指标纯函数**与
**因果训练变体配置**（超参与口径），用于把方案
``docs/design/p2-7-causal-kg-debate-v1/DESIGN.md`` §4 的口径钉死。
配套入口 ``ai-service/scripts/build_counterfactual.py``（生成器）与
``ai-service/scripts/eval_counterfactual.py``（评测）已就位。
**但 C1 特征干预构造、C2 反事实配对构造、C3 因果训练均未实现**——
入口显式 ``raise NotImplementedError`` / ``NotImplementedError``，评测侧缺数据一律记 ``NOT_RUN``。

已知缺陷修复（同日验收）：``compare_models`` 曾把 ``holm_bonferroni`` 的返回当 list
取下标（实为 dict，会 KeyError）、误读 bootstrap 的 ``low/high``（实为 ``ci_low/ci_high``，
导致显著性恒为假）；``effective_n`` 曾读不存在的 ``icc["m"]`` 使 DEFF 恒为 1、
有效 n 恒等于名义 n。三处均已修正并加测试钉住。

诚实边界（沿用 §5 统一禁止事项与口径⑲）：
1. 全部结论只针对**合成拓扑 + 合成告警**，不得写成生产性能（M29 口径⑦）。
2. 合成数据的因果结构由**生成器给定**，属**循环披露**范围（C-G2）。
3. 任何增益必须给对照 + 区间 + Holm 校正；不显著一律写「未证明增益」。
"""

from .metrics import (
    collateral_flip_rate,
    compare_models,
    effective_n,
    flip_rate,
    pair_accuracy,
)
from .schema import (
    CounterfactualPair,
    FlipRecord,
    MetricResult,
    PairVerdict,
    Plan,
)
from .training import (
    DEFAULT_REG_WEIGHT,
    REG_WEIGHTS,
    CausalTrainConfig,
    CausalTrainingNotImplemented,
)

__all__ = [
    "Plan",
    "CounterfactualPair",
    "FlipRecord",
    "PairVerdict",
    "MetricResult",
    "flip_rate",
    "collateral_flip_rate",
    "pair_accuracy",
    "compare_models",
    "effective_n",
    "REG_WEIGHTS",
    "DEFAULT_REG_WEIGHT",
    "CausalTrainConfig",
    "CausalTrainingNotImplemented",
]

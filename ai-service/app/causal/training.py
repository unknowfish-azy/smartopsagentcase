# -*- coding: utf-8 -*-
"""P2-7 / C3：因果训练变体（**仅骨架，训练逻辑未实现**）。

方案 §4.2「因果模型」候选 + §4.4（C3）：

1. **反事实数据增强**：用 C1/C2 生成的样本对做对比学习；
2. **因果正则**：在损失里加入「干预后排序应改变」的软约束，权重作为超参做
   消融（``REG_WEIGHTS`` 三档：0 / 0.5 / 1.0）。

⚠️ **当前状态（2026-11-24）**：两者**均未实现**，入口显式抛错。骨架阶段只固定
超参与口径，避免后续接线时凭空发明参数。

硬约束（§4.5 C-G5）：除非 C-G3（``a1_gain`` 在 Holm 校正后显著且区间不含 0）通过，
**线上默认仍是原模型**。本模块不得被默认训练链路引用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

# 因果正则权重的消融档位（§4.4 C3 要求「超参消融 3 档」）。
REG_WEIGHTS: tuple[float, ...] = (0.0, 0.5, 1.0)

# 默认必须是「不使用因果正则」的那一档——C-G5：默认不变。
DEFAULT_REG_WEIGHT = 0.0


class CausalTrainingNotImplemented(NotImplementedError):
    """因果训练变体尚未实现——禁止以「跑过训练」名义产出未经评测的模型。"""


@dataclass(frozen=True)
class CausalTrainConfig:
    """因果变体训练配置（消融超参 + 可复现种子）。"""

    base_model: str
    variant: str                     # "counterfactual_augmentation" | "causal_regularizer"
    reg_weight: float = DEFAULT_REG_WEIGHT
    seed: int = 20261125
    epochs: int = 5                  # §4.6 风险 3：限 seeds 与 epochs
    n_seeds: int = 5

    def validate(self) -> None:
        if self.variant not in {"counterfactual_augmentation", "causal_regularizer"}:
            raise ValueError(
                f"未知 variant={self.variant!r}；骨架只登记上述两种候选"
            )
        if self.reg_weight not in REG_WEIGHTS:
            raise ValueError(
                f"reg_weight 必须取 {REG_WEIGHTS} 之一（消融档位），"
                f"当前 {self.reg_weight!r}"
            )
        if self.n_seeds < 5:
            raise ValueError("n_seeds 至少 5（§4.6 风险 3）")
        if self.epochs <= 0:
            raise ValueError("epochs 必须是正整数")

    @property
    def is_default_behaviour(self) -> bool:
        """正则权重为 0 时，行为应与原模型一致（C-G5 的守卫）。"""

        return self.reg_weight == 0.0 and self.variant == "causal_regularizer"

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_model": self.base_model,
            "variant": self.variant,
            "reg_weight": self.reg_weight,
            "seed": self.seed,
            "epochs": self.epochs,
            "n_seeds": self.n_seeds,
        }


def causal_regularization_loss(
    config: CausalTrainConfig,
    ranking_before: Sequence[float],
    ranking_after: Sequence[float],
) -> float:
    """「干预后排序应改变」的软约束项（未实现）。

    预期语义：对同一事件，若干预真根因特征后模型排序**几乎不变**，则施加惩罚；
    权重的绝对尺度需与原损失对齐后才能并入总损失。
    """

    raise CausalTrainingNotImplemented(
        "因果正则项未实现（骨架阶段）。实现时须先定义「排序变化」的度量，"
        "并说明该正则为何对应因果性而非仅是敏感性。"
    )


def counterfactual_augmentation_pairs(plan: Any) -> list[dict[str, Any]]:
    """从 Plan 派生反事实增强样本对（未实现；依赖 C1/C2 生成器）。"""

    raise CausalTrainingNotImplemented(
        "反事实增强未实现（骨架阶段）；它依赖 build_counterfactual.py 的 C1/C2 生成器。"
    )


__all__ = [
    "REG_WEIGHTS",
    "DEFAULT_REG_WEIGHT",
    "CausalTrainConfig",
    "CausalTrainingNotImplemented",
    "causal_regularization_loss",
    "counterfactual_augmentation_pairs",
]

# -*- coding: utf-8 -*-
"""P2-7 / C 的数据契约（骨架）。

这里只**定义形状与校验**，不含任何构造逻辑：
- `Plan`            ：一次反事实评测的生成参数（写进数据卡，保证可复现）；
- `CounterfactualPair`：C2 配对样本记录（同拓扑、同噪声、仅根因节点不同）；
- `FlipRecord`      ：C1 干预后的逐样本判定记录（改判 / 误伤都靠它区分）；
- `PairVerdict`     ：C2 配对的逐对判定；
- `MetricResult`    ：统一指标输出（值 + n + Wilson + status + 备注）。

⚠️ 骨架边界：**没有**任何函数能凭空生成上述样本。生成器见
``ai-service/scripts/build_counterfactual.py``（未实现，显式抛错）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class PlanError(ValueError):
    """生成计划非法（缺字段 / 越界 / 自相矛盾）。"""


@dataclass(frozen=True)
class Plan:
    """一次反事实评测的生成参数。

    对应 §4.4 的 C1（干预构造）+ C2（配对构造）参数；C-G1 要求「同种子重跑逐位一致」，
    因此 ``seed`` 必须落盘，且所有生成步骤只能经由它派生随机性。
    """

    scenario: str
    model: str
    seed: int
    n_events: int
    n_pairs: int = 0
    do_node_policy: str = "true_root"   # C1: do(x_v <- 0)，v = 真根因节点
    mask_value: float = 0.0
    alpha: float = 0.05
    n_boot: int = 5000
    note: str = ""

    def validate(self) -> None:
        if not self.scenario or not isinstance(self.scenario, str):
            raise PlanError("scenario 必须是非空字符串")
        if not self.model or not isinstance(self.model, str):
            raise PlanError("model 必须是非空字符串")
        if not isinstance(self.seed, int) or self.seed < 0:
            raise PlanError("seed 必须是非负整数")
        if not isinstance(self.n_events, int) or self.n_events <= 0:
            raise PlanError("n_events 必须是正整数")
        if not isinstance(self.n_pairs, int) or self.n_pairs < 0:
            raise PlanError("n_pairs 必须是非负整数")
        if self.do_node_policy != "true_root":
            raise PlanError(
                f"do_node_policy 仅支持 'true_root'（当前 {self.do_node_policy!r}）"
            )
        if not 0.0 < self.alpha < 1.0:
            raise PlanError("alpha 必须落在 (0, 1)")
        if not isinstance(self.n_boot, int) or self.n_boot < 100:
            raise PlanError("n_boot 至少 100（小样本区间不可解释）")

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Plan":
        if not isinstance(raw, dict):
            raise PlanError("plan 必须是 JSON 对象")
        known = {
            "scenario", "model", "seed", "n_events", "n_pairs",
            "do_node_policy", "mask_value", "alpha", "n_boot", "note",
        }
        unknown = sorted(set(raw) - known)
        if unknown:
            raise PlanError(f"plan 含未知字段：{unknown}")
        plan = cls(**raw)
        plan.validate()
        return plan

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "model": self.model,
            "seed": self.seed,
            "n_events": self.n_events,
            "n_pairs": self.n_pairs,
            "do_node_policy": self.do_node_policy,
            "mask_value": self.mask_value,
            "alpha": self.alpha,
            "n_boot": self.n_boot,
            "note": self.note,
        }


@dataclass(frozen=True)
class CounterfactualPair:
    """C2 反事实配对：同拓扑、同噪声，仅根因节点不同（v vs w）。"""

    pair_id: str
    topology_id: str
    root_v: str
    root_w: str
    sample_v_ref: str
    sample_w_ref: str

    def validate(self) -> None:
        for name in ("pair_id", "topology_id", "root_v", "root_w",
                     "sample_v_ref", "sample_w_ref"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise PlanError(f"CounterfactualPair.{name} 必须是非空字符串")
        if self.root_v == self.root_w:
            raise PlanError("C2 配对的两个根因节点必须不同（否则不构成反事实对）")

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair_id": self.pair_id,
            "topology_id": self.topology_id,
            "root_v": self.root_v,
            "root_w": self.root_w,
            "sample_v_ref": self.sample_v_ref,
            "sample_w_ref": self.sample_w_ref,
        }


@dataclass(frozen=True)
class FlipRecord:
    """C1 干预后的逐样本判定。

    ``is_true_root=False`` 的记录用于**误伤率**（对非根因节点干预时也改判），
    方案 §4.6 风险 2 明确要求两者一起看——单看 flip_rate 会被平凡规则刷满。
    """

    case_id: str
    model: str
    intervened_node: str
    is_true_root: bool
    top1_before: str | None
    top1_after: str | None

    @property
    def flipped(self) -> bool | None:
        """True=改判；None=前后任一缺失（不可判定，**不计入分母**）。"""

        if self.top1_before is None or self.top1_after is None:
            return None
        return self.top1_before != self.top1_after

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "model": self.model,
            "intervened_node": self.intervened_node,
            "is_true_root": self.is_true_root,
            "top1_before": self.top1_before,
            "top1_after": self.top1_after,
        }


@dataclass(frozen=True)
class PairVerdict:
    """C2 配对的逐对判定：模型是否把**真根因**排在前面。"""

    pair_id: str
    preferred_correct: bool
    margin: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair_id": self.pair_id,
            "preferred_correct": self.preferred_correct,
            "margin": self.margin,
        }


@dataclass(frozen=True)
class MetricResult:
    """统一指标输出；``status`` 取 ``COMPLETED`` / ``NOT_RUN`` / ``INSUFFICIENT_DATA``。"""

    name: str
    value: float | None
    n: int
    status: str
    wilson_95: tuple[float, float] | None = None
    note: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "n": self.n,
            "status": self.status,
            "wilson_95": list(self.wilson_95) if self.wilson_95 else None,
            "note": self.note,
            **self.extra,
        }


__all__ = [
    "PlanError",
    "Plan",
    "CounterfactualPair",
    "FlipRecord",
    "PairVerdict",
    "MetricResult",
]

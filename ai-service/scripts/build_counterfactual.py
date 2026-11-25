"""P2-7 / C1：反事实样本构造器（**仅骨架，生成逻辑未实现**）。

方案：``docs/design/p2-7-causal-kg-debate-v1/DESIGN.md`` §4.4（C1）+ §4.5（C-G1/C-G2）。

本脚本**只负责**：
1. 把生成参数收敛成 ``app.causal.schema.Plan`` 并校验（非法计划直接拒绝执行）；
2. 落盘**数据卡**（plan + 状态 + 时间戳），保证 C-G1「同种子重跑逐位一致」所需的
   参数可追溯；
3. 给出生成器入口函数——但**故意不实现**：调用即 ``raise NotImplementedError``。

⚠️ **当前状态（2026-11-24）**：C1 特征干预（``do(x_v <- 0)``）与 C2 反事实配对
**均未实现**（用户指令：「先按方案 §4 搭个骨架，反事实先不写」）。因此本脚本
**不产出任何样本**，只产出数据卡与显式未实现状态。

用法：::

    python ai-service/scripts/build_counterfactual.py \
        --scenario synthetic-topology-v1 --model graphsage --seed 20261125 \
        --n-events 200 --n-pairs 100 --out data/counterfactual/card.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

AI_SERVICE = Path(__file__).resolve().parents[1]
REPO_ROOT = AI_SERVICE.parent
for _path in (str(AI_SERVICE), str(REPO_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from app.causal.schema import Plan, PlanError  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GENERATOR_VERSION = "skeleton-20261125"
IMPLEMENTATION_STATUS = "NOT_IMPLEMENTED"


class GeneratorNotImplemented(NotImplementedError):
    """反事实生成器尚未实现——显式抛错，禁止静默产出空样本冒充结果。"""


def generate_c1_interventions(plan: Plan) -> list[dict[str, Any]]:
    """C1 特征干预：对真根因节点 ``v`` 做 ``do(x_v <- mask_value)``，其余不变。

    未实现。实现后应返回逐样本记录（对应 ``FlipRecord.to_dict()`` 的形状），
    且同一 ``plan.seed`` 下逐位可复现（C-G1）。
    """

    raise GeneratorNotImplemented(
        "C1 特征干预生成器未实现（骨架阶段）。实现要点见 DESIGN §4.2 C1："
        "只遮蔽真根因节点的因果特征，其余特征与噪声保持不变。"
    )


def generate_c2_pairs(plan: Plan) -> list[dict[str, Any]]:
    """C2 反事实配对：同拓扑、同噪声，仅根因节点不同（``v`` vs ``w``）。

    未实现。实现后应返回配对记录（对应 ``CounterfactualPair.to_dict()`` 的形状）。
    """

    raise GeneratorNotImplemented(
        "C2 反事实配对生成器未实现（骨架阶段）。实现要点见 DESIGN §4.2 C2："
        "配对必须共享拓扑与噪声，只有根因节点不同，否则 pair_accuracy 不可解释。"
    )


def build_card(plan: Plan, *, requested: Sequence[str]) -> dict[str, Any]:
    """组装数据卡：参数 + 显式未实现状态 + 循环披露（C-G2）。"""

    return {
        "generator_version": GENERATOR_VERSION,
        "implementation_status": IMPLEMENTATION_STATUS,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "plan": plan.to_dict(),
        "requested_generators": list(requested),
        "artifacts": [],
        "loop_disclosure": (
            "合成数据的因果结构由生成器给定（C-G2）：结论只说明模型在该生成器下的"
            "相对优劣，不得外推为生产因果推断（M29 口径⑦）。"
        ),
        "notes": (
            "骨架阶段：生成器未实现，本卡不描述任何样本。C-G1 要求同种子重跑逐位一致，"
            "故 seed 必须落盘且所有随机性只能由它派生。"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="P2-7/C 反事实样本构造器（骨架；生成逻辑未实现）",
    )
    parser.add_argument("--scenario", required=True, help="场景名（写入数据卡）")
    parser.add_argument("--model", required=True, help="被评测模型标识（写入数据卡）")
    parser.add_argument("--seed", type=int, default=20261125)
    parser.add_argument("--n-events", type=int, required=True, help="C1 干预样本数")
    parser.add_argument("--n-pairs", type=int, default=0, help="C2 配对数（0=不生成）")
    parser.add_argument("--mask-value", type=float, default=0.0, help="do() 的遮蔽取值")
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--n-boot", type=int, default=5000)
    parser.add_argument("--note", default="")
    parser.add_argument("--out", required=True, help="数据卡输出路径（JSON）")
    args = parser.parse_args(argv)

    try:
        plan = Plan(
            scenario=args.scenario,
            model=args.model,
            seed=args.seed,
            n_events=args.n_events,
            n_pairs=args.n_pairs,
            mask_value=args.mask_value,
            alpha=args.alpha,
            n_boot=args.n_boot,
            note=args.note,
        )
        plan.validate()
    except PlanError as exc:
        print(f"[error] 生成计划非法：{exc}")
        return 2

    requested = ["c1_interventions"] + (["c2_pairs"] if plan.n_pairs > 0 else [])
    card = build_card(plan, requested=requested)

    # 骨架阶段：仍然执行入口，让「未实现」这件事在运行时被显式验证，
    # 而不是静默跳过（否则后续接线时容易把空产物当成有效数据）。
    for name in requested:
        try:
            {"c1_interventions": generate_c1_interventions,
             "c2_pairs": generate_c2_pairs}[name](plan)
        except GeneratorNotImplemented as exc:
            print(f"[skeleton] {name}：{exc}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] 数据卡已写入 {out}（status={IMPLEMENTATION_STATUS}，未产出样本）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

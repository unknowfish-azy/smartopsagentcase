"""PROBE-P1-01 对照实验：加权缺口覆盖 vs 同预算固定顺序补证调度。

规则来源：任务书 PROBE-P1-01 验收——"与同目录、同预算、同停止机会的
固定顺序策略比较，所有失败/暂缓均入报告；不承诺贪心全局最优。"

实验设计：
- 同一契约（3 个必需义务，权重 1/2/3）、同一登记表（4 个探针）、
  每个策略独立新建 RunBudget（12 次 / 30 秒，常量来自冻结 schema）。
- 两个策略共享 choose_next 的全部过滤与 WAIT/STOP 规则，唯一差异是
  合格候选的排序：(-score, cost, probe_id) vs probe_id 升序。
- S1 所有探针都产生有效信息；S2 中高覆盖探针 probe-wide 不产生新增
  有效信息（按 §5 记账为 exhausted）。两个场景原样入报告，不做择优陈述。

运行：python scripts/compare_probe_strategies.py
输出：docs/development/probe-p1-01-evidence/compare-weighted-vs-fixed-order.json
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from agent.recovery_contracts import (  # noqa: E402
    ObligationResult,
    Probe,
    ProbeRegistry,
    RecoveryContract,
    RunBudget,
    choose_next,
    choose_next_fixed_order,
    object_digest,
    parse_time,
    utc_now,
)

FIXTURE = REPO_ROOT / "tests" / "recovery_contracts" / "fixtures" / "vp01-positive.json"
OUTPUT = (
    REPO_ROOT / "docs" / "development" / "probe-p1-01-evidence"
    / "compare-weighted-vs-fixed-order.json"
)
DECISION_TIME = "2026-11-05T02:00:06Z"
OBLIGATION_WEIGHTS = (("obl-a", 1), ("obl-b", 2), ("obl-c", 3))


def build_contract() -> RecoveryContract:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))["input"]["contract"]
    raw = copy.deepcopy(raw)
    base = raw["obligations"][0]
    raw["obligations"] = []
    for obligation_id, weight in OBLIGATION_WEIGHTS:
        obligation = copy.deepcopy(base)
        obligation["obligation_id"] = obligation_id
        obligation["weight"] = weight
        raw["obligations"].append(obligation)
    raw["digest"] = object_digest({k: v for k, v in raw.items() if k != "digest"})
    return RecoveryContract.from_dict(raw)


def build_registry() -> ProbeRegistry:
    def probe(probe_id: str, covers: tuple[str, ...], cost: int, collector: str,
              group: str) -> Probe:
        return Probe(
            probe_id=probe_id,
            collector_id=collector,
            collector_version="1.0.0",
            obligation_ids=covers,
            cost=cost,
            permission="probe:read",
            read_only=True,
            endpoint="http://127.0.0.1:18081",
            path="/health",
            target_id="service:edge-nginx",
            source_group=group,
        )

    registry = ProbeRegistry()
    registry.register(probe("probe-cheap-a", ("obl-a",), 1, "col-a", "sg-a"))
    registry.register(probe("probe-cheap-b", ("obl-b",), 1, "col-b", "sg-b"))
    registry.register(probe("probe-cheap-c", ("obl-c",), 1, "col-b", "sg-b"))
    registry.register(
        probe("probe-wide", ("obl-a", "obl-b", "obl-c"), 1, "col-a", "sg-a")
    )
    return registry


def all_unknown(contract: RecoveryContract) -> list[ObligationResult]:
    checked_at = parse_time(DECISION_TIME)
    return [
        ObligationResult(
            obligation_id=obligation.obligation_id,
            value="UNKNOWN",
            reason_codes=("MISSING",),
            used_evidence_ids=(),
            rejected_evidence=(),
            checked_at=checked_at,
        )
        for obligation in contract.obligations
    ]


def run_strategy(
    contract: RecoveryContract,
    registry: ProbeRegistry,
    chooser,
    outcomes: dict[str, str],
) -> dict:
    """跑一个策略直到 STOP；outcome: success→覆盖义务置 TRUE，no_progress→记 exhausted。"""
    results = {r.obligation_id: r for r in all_unknown(contract)}
    budget = RunBudget.from_contract(contract, run_id="run-compare", started_at=DECISION_TIME)
    exhausted: set[str] = set()
    trace: list[dict] = []

    for step in range(contract.budgets.max_probe_calls + 2):
        decision = chooser(
            contract,
            list(results.values()),
            registry,
            budget,
            DECISION_TIME,
            permissions={"probe:read"},
            exhausted_probe_ids=exhausted,
        )
        entry = {
            "step": step,
            "decision": decision["decision"],
            "selected_probe_id": decision["selected_probe_id"],
            "score": decision["score"],
            "stop_reason": decision["stop_reason"],
            "budget_before": decision["budget_before"],
            "budget_after": decision["budget_after"],
            "candidates": decision["candidates"],
        }
        if decision["extensions"]:
            entry["extensions"] = decision["extensions"]
        trace.append(entry)

        if decision["decision"] == "STOP":
            break
        if decision["decision"] == "WAIT":
            # 本实验不构造未来采样槽；WAIT 原样记录后终止，等待不扣费。
            break

        probe_id = decision["selected_probe_id"]
        budget.record_call()
        outcome = outcomes.get(probe_id, "success")
        if outcome == "success":
            probe = registry.get(probe_id)
            for obligation_id in probe.obligation_ids:
                if obligation_id in results:
                    results[obligation_id] = ObligationResult(
                        obligation_id=obligation_id,
                        value="TRUE",
                        reason_codes=(),
                        used_evidence_ids=(f"obs-{step}-{probe_id}",),
                        rejected_evidence=(),
                        checked_at=parse_time(DECISION_TIME),
                    )
        else:
            # 无新增有效信息：按 §5 记账为 exhausted，不删除历史。
            exhausted.add(probe_id)

    return {
        "trace": trace,
        "calls_used": budget.calls_used,
        "final_decision": trace[-1]["decision"],
        "final_stop_reason": trace[-1]["stop_reason"],
        "true_obligations": sorted(
            obligation_id for obligation_id, r in results.items() if r.value == "TRUE"
        ),
    }


def main() -> None:
    contract = build_contract()
    registry = build_registry()
    scenarios = [
        (
            "S1-uniform-success",
            "所有探针调用都产生新增有效信息",
            {},
        ),
        (
            "S2-wide-no-progress",
            "probe-wide 高覆盖但不产生新增有效信息（贪心非全局最优的反例）",
            {"probe-wide": "no_progress"},
        ),
    ]

    report = {
        "experiment_id": "probe-p1-01-weighted-vs-fixed-order",
        "generated_at": utc_now().isoformat().replace("+00:00", "Z"),
        "contract_digest": contract.digest,
        "budget_constants": {
            "max_probe_calls": contract.budgets.max_probe_calls,
            "per_probe_timeout_ms": contract.budgets.per_probe_timeout_ms,
            "run_deadline_ms": contract.budgets.run_deadline_ms,
            "evidence_ttl_ms": contract.budgets.evidence_ttl_ms,
        },
        "registry": [
            {
                "probe_id": probe.probe_id,
                "obligation_ids": list(probe.obligation_ids),
                "cost": probe.cost,
                "collector_id": probe.collector_id,
                "source_group": probe.source_group,
            }
            for probe in registry.probes()
        ],
        "scenarios": [],
        "comparison_notes": (
            "同一登记表、同一契约、同预算常量与同停止规则；唯一差异是合格候选排序。"
            "S1 加权策略 1 次调用完成覆盖，固定顺序 3 次；S2 加权策略先选无信息探针，"
            "反而比固定顺序多用 1 次调用。两组结果仅说明可解释的对照差异，"
            "不构成“贪心更省调用”的全局主张。"
        ),
    }

    for scenario_id, description, outcomes in scenarios:
        weighted = run_strategy(contract, registry, choose_next, outcomes)
        fixed = run_strategy(contract, registry, choose_next_fixed_order, outcomes)
        report["scenarios"].append(
            {
                "scenario_id": scenario_id,
                "description": description,
                "outcomes": outcomes or "全部 success",
                "weighted_coverage_per_cost": weighted,
                "fixed_order_by_probe_id": fixed,
            }
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for scenario in report["scenarios"]:
        weighted = scenario["weighted_coverage_per_cost"]
        fixed = scenario["fixed_order_by_probe_id"]
        print(
            f"{scenario['scenario_id']}: weighted calls={weighted['calls_used']} "
            f"stop={weighted['final_stop_reason']} | fixed calls={fixed['calls_used']} "
            f"stop={fixed['final_stop_reason']}"
        )
    print(f"written: {OUTPUT}")


if __name__ == "__main__":
    main()

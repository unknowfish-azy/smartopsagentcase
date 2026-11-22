"""EXP-DEBATE-001：多 Agent 辩论（P2-7 / A）受控集对照实验。

对照什么
--------
同一批受控样本，比较

* **基线**：每个角色**单独**取证（只看自己通道）后给结论；
* **实验**：四角色辩论（round 0 独立 → round 1+ 反驳 → 仲裁）。

指标
----
- 协议（主）：``convergence_rate`` / ``changed_rate`` / ``escalated_rate``
  / ``mean_rounds``；``escalated`` **单独计数，不从分母剔除**（门禁 A-G3）。
- 准确（次）：``root_cause_accuracy`` + Wilson 区间；配对 McNemar（辩论 vs 每个
  单角色基线）+ Holm 校正（门禁 A-G4）。
- 有效样本量：按 ``root_cause_group`` 分组算 ICC(1) → DEFF → 有效 n。

诚实边界（必须随结果引用，门禁 A-G5）
----------------------------------
1. ``PROBE_TYPE_CANDIDATES`` 是**人工按探针语义拟定**的封闭词表，
   **不是**从数据里学出来的模型；因此准确率反映的是**命名/语义一致性**，
   不是推理能力，**禁止**写成「多 Agent 辩论提升准确率 X%」。
2. 受控集为**合成 fixture**（``source.data_class=SYNTHETIC``），
   且 M31 已判定主指标存在「标签—探针循环」；本实验的准确率**不得**
   当作真实分布性能。
3. 未收敛（``escalated``）一律记为**无结论**，不粉饰成「达成一致」。

负对照（门禁 A-G2）
-------------------
``--negative-control`` 把所有证据发给所有角色（共享证据池），
隔离校验必须判 ``valid=False``；报告里单独落盘。

产物
----
- ``reports/debate-eval-<tag>.json``
- ``reports/debate-eval-<tag>.md``

复现：``python scripts/eval_debate.py``（默认 ``--split test``）
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from agent.subagents.debate import DEBATE_ROLE_NAMES, DebateRunner
from agent.subagents.debate_rules import PROBE_TYPE_CANDIDATES, RuleRoleAgent
from agent.subagents.evidence_channels import (
    CHANNEL_PROBE_TYPES,
    ChannelView,
    EvidenceItem,
    partition_items,
    shared_pool_views,
    validate_isolation,
)

_STATS_PATH = REPO / "scripts" / "stats_inference.py"
_spec = importlib.util.spec_from_file_location("stats_inference", _STATS_PATH)
assert _spec and _spec.loader
stats = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(stats)

SPLIT_DIR = REPO / "SmartOps-Dataset" / "Controlled" / "v1" / "splits"
DEFAULT_REPORT_DIR = REPO / "reports"

ALPHA = 0.05
MAX_REBUTTAL_ROUNDS = 2
SEED = 20261122


# ---------------------------------------------------------------------------
# 数据装载
# ---------------------------------------------------------------------------


def load_samples(split: str, split_dir: Path) -> list[dict[str, Any]]:
    path = split_dir / f"{split}.jsonl"
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return [row for row in rows if row.get("dataset_type") == "verification"]


def build_items(sample: dict[str, Any]) -> list[EvidenceItem]:
    """把受控样本的 state_assertions 转成证据项，id 优先取 evidence[]。"""

    assertions = sample.get("state_assertions") or []
    registered = sample.get("evidence") or []
    items: list[EvidenceItem] = []
    for index, assertion in enumerate(assertions):
        evidence_id = (
            registered[index].get("evidence_id")
            if index < len(registered) and registered[index].get("evidence_id")
            else f"EV-{sample['sample_id']}-{index + 1:02d}"
        )
        items.append(EvidenceItem(
            evidence_id=evidence_id,
            probe_type=assertion["type"],
            target=str(assertion.get("target", "")),
            summary=str(assertion.get("description", "")),
        ))
    return items


def _ratio(num: int | None, den: int | None) -> dict[str, Any]:
    if num is None or den in (None, 0):
        return {"num": num, "den": den, "value": None, "status": "NOT_RUN"}
    lo, hi = stats.wilson_interval(num, den)
    return {
        "num": num, "den": den,
        "value": round(num / den, 6),
        "status": "COMPLETED",
        "wilson_95": [round(lo, 4), round(hi, 4)],
    }


# ---------------------------------------------------------------------------
# 实验
# ---------------------------------------------------------------------------


def run_experiment(samples: list[dict[str, Any]]) -> dict[str, Any]:
    agent = RuleRoleAgent()
    runner = DebateRunner(agent, max_rebuttal_rounds=MAX_REBUTTAL_ROUNDS)

    rows: list[dict[str, Any]] = []
    for sample in samples:
        group = sample["ground_truth"]["root_cause_group"]
        question = sample.get("instruction") or sample.get("claim") or sample["sample_id"]
        items = build_items(sample)
        views = partition_items(items)

        solo = {role: agent.conclude(role, question, views[role])
                for role in DEBATE_ROLE_NAMES}
        record = runner.run(question, views)
        # 覆盖对照：把所有通道的证据一次性给同一个角色（无辩论）。
        # 用来区分「增益来自通道覆盖」还是「增益来自辩论协议」——
        # 若两者准确率相同，则本实验证明的是覆盖，不是辩论。
        oracle = agent.conclude(
            "_coverage_oracle", question, ChannelView(role="_coverage_oracle",
                                                       items=tuple(items))
        )

        final = record.rounds[-1]
        cited: list[str] = []
        for conclusion in final.values():
            cited.extend(conclusion.evidence)
        supporting = [
            eid for eid in cited
            if eid in {item.evidence_id for item in items
                       if group in PROBE_TYPE_CANDIDATES.get(item.probe_type, ())}
        ]

        rows.append({
            "sample_id": sample["sample_id"],
            "root_cause_group": group,
            "n_channels": sum(1 for view in views.values() if not view.empty),
            "solo_top1": {role: solo[role].top1 for role in DEBATE_ROLE_NAMES},
            "solo_correct": {
                role: bool(solo[role].top1) and solo[role].top1 == group
                for role in DEBATE_ROLE_NAMES
            },
            "debate_top1": record.verdict.final_top1,
            "debate_correct": bool(record.verdict.final_top1)
                              and record.verdict.final_top1 == group,
            "coverage_oracle_top1": oracle.top1,
            "coverage_oracle_correct": bool(oracle.top1) and oracle.top1 == group,
            "verdict": record.verdict.to_dict(),
            "n_cited_evidence": len(cited),
            "n_supporting_evidence": len(supporting),
        })

    converged = [r for r in rows if r["verdict"]["converged"]]
    escalated = [r for r in rows if r["verdict"]["status"] == "escalated"]
    changed = [r for r in rows if r["verdict"]["changed"]]

    solo_metrics = {
        role: {
            "accuracy": _ratio(
                sum(1 for r in rows if r["solo_correct"][role]), len(rows)
            ),
            "abstain_rate": _ratio(
                sum(1 for r in rows if r["solo_top1"][role] is None), len(rows)
            ),
            "n_correct": sum(1 for r in rows if r["solo_correct"][role]),
        }
        for role in DEBATE_ROLE_NAMES
    }

    debate_accuracy = _ratio(
        sum(1 for r in rows if r["debate_correct"]), len(rows)
    )
    oracle_accuracy = _ratio(
        sum(1 for r in rows if r["coverage_oracle_correct"]), len(rows)
    )
    n_debate_differs = sum(
        1 for r in rows
        if r["debate_top1"] != r["coverage_oracle_top1"]
    )

    cited_total = sum(r["n_cited_evidence"] for r in rows)
    supporting_total = sum(r["n_supporting_evidence"] for r in rows)

    return {
        "rows": rows,
        "n_samples": len(rows),
        "protocol": {
            "convergence_rate": _ratio(len(converged), len(rows)),
            "escalated_rate": _ratio(len(escalated), len(rows)),
            "changed_rate": _ratio(len(changed), len(rows)),
            "mean_rounds": (
                round(sum(r["verdict"]["rounds"] for r in rows) / len(rows), 4)
                if rows else None
            ),
            "n_converged": len(converged),
            "n_escalated": len(escalated),
            "n_changed": len(changed),
            "n_multi_channel": sum(1 for r in rows if r["n_channels"] >= 2),
            "verdict_status_distribution": dict(Counter(r["verdict"]["status"] for r in rows)),
            "rounds_distribution": dict(Counter(r["verdict"]["rounds"] for r in rows)),
        },
        "accuracy": {
            "debate": debate_accuracy,
            "coverage_oracle": oracle_accuracy,
            "n_debate_differs_from_oracle": n_debate_differs,
            "solo": solo_metrics,
            "evidence_precision": _ratio(supporting_total, cited_total),
            "n_cited_evidence": cited_total,
            "n_supporting_evidence": supporting_total,
        },
    }


def pairwise_comparison(block: dict[str, Any]) -> dict[str, Any]:
    """辩论 vs 每个单角色基线：配对 McNemar + Holm（4 个比较）。"""

    rows = block["rows"]
    debate_correct = [r["debate_correct"] for r in rows]

    results: list[dict[str, Any]] = []
    p_values: list[float] = []
    labels: list[str] = []
    conditions: list[tuple[str, list[bool]]] = [
        (f"solo:{role}", [r["solo_correct"][role] for r in rows])
        for role in DEBATE_ROLE_NAMES
    ]
    # 覆盖对照：全证据单角色（无辩论）。若与辩论准确率相同 → 增益来自覆盖。
    conditions.append(
        ("coverage_oracle", [r["coverage_oracle_correct"] for r in rows])
    )

    for name, correct in conditions:
        comparison = stats.compare_paired_classifiers(
            debate_correct, correct, alpha=ALPHA
        )
        entry = {
            "pair": f"debate vs {name}",
            "n": comparison["n"],
            "debate_accuracy": comparison["a_accuracy"],
            "baseline_accuracy": comparison["b_accuracy"],
            "mcnemar": comparison["mcnemar"],
        }
        results.append(entry)
        if comparison["mcnemar"].get("status") == "COMPLETED":
            p_values.append(comparison["mcnemar"]["p_value"])
            labels.append(entry["pair"])

    holm = None
    if p_values:
        holm = stats.holm_bonferroni(p_values, alpha=ALPHA, labels=labels)
        by_label = {item["label"]: item for item in holm["items"]}
        for entry in results:
            item = by_label.get(entry["pair"])
            if item:
                entry["holm_adjusted_p"] = item["adjusted_p"]
                entry["holm_reject"] = item["reject"]

    return {"comparisons": results, "holm": holm}


def effective_sample_size(block: dict[str, Any]) -> dict[str, Any]:
    """按 root_cause_group 分组算 ICC(1) → DEFF → 有效 n。"""

    by_group: dict[str, list[float]] = defaultdict(list)
    for row in block["rows"]:
        by_group[row["root_cause_group"]].append(1.0 if row["debate_correct"] else 0.0)

    groups: Sequence[Sequence[float]] = [by_group[g] for g in sorted(by_group)]
    icc = stats.icc_one_way(groups)
    n = len(block["rows"])
    deff = None
    eff_n = None
    if icc.get("status") == "COMPLETED" and icc.get("icc") is not None:
        sizes = [len(g) for g in groups]
        m = sum(sizes) / len(sizes) if sizes else 0.0
        deff = round(stats.design_effect(m, icc["icc"]), 6)
        eff_n = round(stats.effective_n(n, deff), 4)

    return {
        "grouping": "root_cause_group",
        "n_groups": len(groups),
        "n_total": n,
        "icc": icc,
        "design_effect": deff,
        "effective_n": eff_n,
    }


# ---------------------------------------------------------------------------
# 负对照（门禁 A-G2）
# ---------------------------------------------------------------------------


def negative_control(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """共享证据池必须被判为无效实验。"""

    all_items = [item for sample in samples for item in build_items(sample)]
    views = shared_pool_views(all_items)
    report = validate_isolation(views)
    return {
        "description": "所有角色看到同一份证据池（同源自证）",
        "n_items": len(all_items),
        "must_be_invalid": True,
        "passed": report.valid is False,
        "report": report.to_dict(),
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EXP-DEBATE-001 多 Agent 辩论受控集对照")
    parser.add_argument("--split", default="test")
    parser.add_argument("--split-dir", default=str(SPLIT_DIR))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--tag", default="controlled-test")
    args = parser.parse_args(argv)

    samples = load_samples(args.split, Path(args.split_dir))
    if not samples:
        print(f"[warn] split={args.split} 没有 verification 样本")
        return 1

    block = run_experiment(samples)
    isolation = validate_isolation(
        partition_items([item for sample in samples for item in build_items(sample)])
    )
    payload = {
        "experiment_id": "EXP-DEBATE-001",
        "dataset_id": "smartops-controlled",
        "dataset_version": "v1",
        "split": args.split,
        "tag": args.tag,
        "n_samples": block["n_samples"],
        "status": "COMPLETED_WITH_LIMITATIONS",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "roles": list(DEBATE_ROLE_NAMES),
            "max_rebuttal_rounds": MAX_REBUTTAL_ROUNDS,
            "agent": "RuleRoleAgent（离线确定性规则，非 LLM）",
            "candidate_table": "agent/subagents/debate_rules.py::PROBE_TYPE_CANDIDATES",
        },
        "stats": {
            "module": "scripts/stats_inference.py",
            "seed": SEED,
            "alpha": ALPHA,
            "paired_test": "McNemar exact binomial",
            "multiplicity": "Holm-Bonferroni over 5 comparisons",
            "coverage_control": "全证据单角色（无辩论），用于区分覆盖增益与辩论增益",
        },
        "channel_isolation": isolation.to_dict(),
        "negative_control": negative_control(samples),
        "protocol_metrics": block["protocol"],
        "accuracy": block["accuracy"],
        "effective_n": effective_sample_size(block),
        "pairwise_comparison": pairwise_comparison(block),
        "rows": block["rows"],
    }

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / f"debate-eval-{args.tag}.json"
    md_path = report_dir / f"debate-eval-{args.tag}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")

    proto = payload["protocol_metrics"]
    print(f"[ok] EXP-DEBATE-001 split={args.split} n={payload['n_samples']}")
    print(f"  收敛={_f(proto['convergence_rate']['value'])} "
          f"未收敛={proto['n_escalated']} "
          f"反驳改判={_f(proto['changed_rate']['value'])} "
          f"平均轮数={proto['mean_rounds']}")
    print(f"  辩论准确率={_f(payload['accuracy']['debate']['value'])} "
          f"有效 n={payload['effective_n']['effective_n']}")
    print(f"  负对照通过={payload['negative_control']['passed']}")
    print(f"[ok] {md_path}")
    return 0


def _f(value: Any) -> str:
    return "  null" if value is None else f"{value:.4f}"


def _ci(item: dict[str, Any]) -> str:
    ci = item.get("wilson_95")
    return "—" if not ci else f"[{ci[0]:.4f}, {ci[1]:.4f}]"


def render_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    a = lines.append
    proto = payload["protocol_metrics"]
    acc = payload["accuracy"]
    eff = payload["effective_n"]

    a("# EXP-DEBATE-001 · 多 Agent 辩论受控集对照")
    a("")
    a(f"> 复现：`python scripts/eval_debate.py --split {payload['split']}` ｜ "
      f"机器结果：`reports/debate-eval-{payload['tag']}.json`")
    a(f"> 运行：{payload['created_at']} ｜ 数据集：`{payload['dataset_id']}:"
      f"{payload['dataset_version']}` split=`{payload['split']}` ｜ n={payload['n_samples']}")
    a("")
    a("## 0. 一句话结论")
    a("")
    a(f"- 协议层面：收敛 {proto['n_converged']}/{payload['n_samples']}"
      f"（{_f(proto['convergence_rate']['value'])}），"
      f"未收敛 {proto['n_escalated']}，反驳后改判 {proto['n_changed']}，"
      f"平均反驳轮数 {proto['mean_rounds']}。")
    a(f"- 准确层面：辩论 {_f(acc['debate']['value'])}，"
      f"单角色最优 {_f(max(v['accuracy']['value'] or 0.0 for v in acc['solo'].values()))}，"
      f"**覆盖对照（全证据单角色、无辩论）{_f(acc['coverage_oracle']['value'])}**；"
      f"有效 n={eff['effective_n']}（分组 {eff['n_groups']} 个 `root_cause_group`）。")
    a(f"- **覆盖 vs 辩论**：辩论与覆盖对照的结论只在 "
      f"{acc['n_debate_differs_from_oracle']}/{payload['n_samples']} 个样本上不同"
      f"（见第 3 节）——若两者准确率相同，则本实验证明的是**通道覆盖**，不是辩论协议。")
    a(f"- 负对照（共享证据池必须判无效）：**{'通过' if payload['negative_control']['passed'] else '未通过'}**。")
    a("")
    a("> ⚠️ **口径**：候选词表为**人工按探针语义拟定**、角色为**离线确定性规则**，"
      "受控集为**合成 fixture**且存在已知的「标签—探针循环」（M31）。"
      "因此准确率反映**命名/语义一致性**，不是推理能力；"
      "**禁止**写成「多 Agent 辩论提升准确率 X%」。")
    a("")
    a("## 1. 协议指标（主）")
    a("")
    a("| 指标 | 值 | n | Wilson 95% |")
    a("|---|---|---|---|")
    a(f"| 收敛率 | {_f(proto['convergence_rate']['value'])} | "
      f"{proto['convergence_rate']['den']} | {_ci(proto['convergence_rate'])} |")
    a(f"| 未收敛率（escalated） | {_f(proto['escalated_rate']['value'])} | "
      f"{proto['escalated_rate']['den']} | {_ci(proto['escalated_rate'])} |")
    a(f"| 反驳改判率（changed） | {_f(proto['changed_rate']['value'])} | "
      f"{proto['changed_rate']['den']} | {_ci(proto['changed_rate'])} |")
    a("")
    a(f"- 平均反驳轮数：{proto['mean_rounds']}（上限 {MAX_REBUTTAL_ROUNDS}）")
    a(f"- 轮数分布：{proto['rounds_distribution']}")
    a(f"- 覆盖 ≥2 条通道的样本：{proto['n_multi_channel']}/{payload['n_samples']}"
      f"（其余样本只有一条通道有证据，辩论退化为单角色）")
    a("")
    a("## 2. 准确性与证据精度（次）")
    a("")
    a("| 条件 | 准确率 | Wilson 95% | 弃权率 |")
    a("|---|---|---|---|")
    a(f"| 辩论（四角色） | {_f(acc['debate']['value'])} | {_ci(acc['debate'])} | — |")
    a(f"| 覆盖对照（全证据单角色，无辩论） | {_f(acc['coverage_oracle']['value'])} | "
      f"{_ci(acc['coverage_oracle'])} | — |")
    for role, metric in acc["solo"].items():
        a(f"| 单角色 {role} | {_f(metric['accuracy']['value'])} | "
          f"{_ci(metric['accuracy'])} | {_f(metric['abstain_rate']['value'])} |")
    a("")
    a(f"- 证据精度（最终引用证据中支持真值组的比例）："
      f"{_f(acc['evidence_precision']['value'])}"
      f"（{acc['n_supporting_evidence']}/{acc['n_cited_evidence']}）")
    a("  - ⚠️ 该指标**循环**：引用证据本身就是按「支持该组」挑选的，"
      "故恒接近 1.0，**不得**当作辩论质量的证据，仅用于确认引用链不空。")
    a("")
    a("## 3. 配对比较（McNemar + Holm）")
    a("")
    a("| 比较 | n | 辩论 | 基线 | b | c | 精确 p | Holm p | 显著 |")
    a("|---|---|---|---|---|---|---|---|---|")
    for entry in payload["pairwise_comparison"]["comparisons"]:
        mc = entry["mcnemar"]
        if mc.get("status") != "COMPLETED":
            a(f"| {entry['pair']} | {entry['n']} | — | — | — | — | — | — | 不可检验 |")
            continue
        a(f"| {entry['pair']} | {entry['n']} | {_f(entry['debate_accuracy'])} | "
          f"{_f(entry['baseline_accuracy'])} | {mc['b']} | {mc['c']} | "
          f"{_f(mc['p_value'])} | {_f(entry.get('holm_adjusted_p'))} | "
          f"{'✓' if entry.get('holm_reject') else '✗'} |")
    a("")
    a("> `coverage_oracle` 一行是**覆盖对照**：同一角色看全量证据、但不辩论。"
      "若「辩论 vs 覆盖对照」无显著差异，则相对单角色的增益**全部来自通道覆盖**，"
      "不是反驳机制——这是本实验最重要的口径。")
    holm = payload["pairwise_comparison"].get("holm")
    if holm:
        a(f"Holm 汇总：{holm['n_reject']}/{holm['n_tests']} 个比较在 α={holm['alpha']} 下显著。")
    a("")
    a("> Holm 校正后**不显著**就必须写「**未证明增益**」，不得写成「无差异」。")
    a("")
    a("## 4. 有效样本量")
    a("")
    a(f"- 分组键：`{eff['grouping']}`，共 {eff['n_groups']} 组，n={eff['n_total']}")
    a(f"- ICC(1)：{_f(eff['icc'].get('icc'))}（status={eff['icc'].get('status')}）")
    a(f"- 设计效应 DEFF：{eff['design_effect']} → 有效 n：{eff['effective_n']}")
    a("")
    a("## 5. 隔离与负对照（门禁 A-G2）")
    a("")
    iso = payload["channel_isolation"]
    a(f"- 通道隔离：`valid={iso['valid']}`，共享对={len(iso['shared_id_pairs'])}，"
      f"越权角色={iso['offending_roles']}")
    nc = payload["negative_control"]
    a(f"- 负对照：{nc['description']}，n_items={nc['n_items']}，"
      f"判 invalid={not nc['report']['valid']} → **{'通过' if nc['passed'] else '未通过'}**")
    a("")
    a("## 6. 局限与禁止口径")
    a("")
    a("1. **合成受控集**：`source.data_class=SYNTHETIC`，非真实分布性能。")
    a("2. **标签—探针循环**：M31 已判定主指标存在生成器侧循环；准确率只作描述。")
    a("3. **无 LLM 成分**：`RuleRoleAgent` 为确定性规则，真实模型路径需另行注入。")
    a("4. **未收敛 ≠ 错误**：`escalated` 记为无结论，单独计数，未从分母剔除。")
    a("5. **单通道样本**：多数样本只有一条通道有证据，辩论在这些样本上退化为单角色；"
      "多通道子集见第 1 节计数。")
    a("6. **禁止**：把本结果写成「多 Agent 辩论提升准确率 X%」或「AI 根因识别准确率」。")
    a("")
    a("## 7. 复现")
    a("")
    a("```bash")
    a("python scripts/eval_debate.py --split test")
    a("python -m pytest tests/agent/test_debate.py")
    a("```")
    a("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())

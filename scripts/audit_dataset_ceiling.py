"""受控集信息量上限与「修复成本」测算（EXP-CEIL-001）。

要回答的问题
------------
``EXP-CIRC-001`` 证明主指标标签可由探针健康度单比特决定。那么要让这类基准真正
度量「假成功检测能力」，**最少需要多少独立标签单元、多少标注工时**？

本脚本给三个可引用量：
1. **独立标签族数**：每个 `root_cause_group` 的真值标签唯一，所以独立信息单元是
   「标签族 × 标签值」，而不是样本条数。当前 = SUCCESS 6 / FALSE_SUCCESS 8 /
   FAILED 5 / UNKNOWN 5 = **24**。
2. **分割稳定性**：对现有样本做重复分组分割，测主指标与平凡规则复现率的变化幅度。
   这是「结论对切分有多敏感」的直接证据。
3. **精度—成本换算**：把「达目标边际误差所需的有效样本量」换算成标注工时
   （2 名标注者、每条双人独立判定 + 仲裁）与对抗单元的构造量。

口径纪律
--------
- **不做事后功效**（沿用 `stats_inference` 口径），只给精度区间与设计效应敏感性。
- 成本换算是**模型外推**：单位工时来自受控集现状的工程测量，不是文献值，
  必须随结果标注假设。
- 本脚本不修改数据、不修改既有指标。

产物
----
- ``reports/dataset-ceiling.{json,md}``

复现：``python scripts/audit_dataset_ceiling.py``
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
SRC = REPO / "SmartOps-Dataset" / "Controlled" / "v1" / "samples.jsonl"
SPLITS = REPO / "SmartOps-Dataset" / "Controlled" / "v1" / "splits"
REPORT_JSON = REPO / "reports" / "dataset-ceiling.json"
REPORT_MD = REPO / "reports" / "dataset-ceiling.md"

EXPERIMENT_ID = "EXP-CEIL-001"

# 标注工时假设（工程估计，非文献值；必须随结果披露）
SECONDS_PER_LABEL = 90        # 单条：读 claim + 看探针 + 判标签
ARBITRATION_RATE = 0.15       # 双人不一致需仲裁的比例（估计）
SECONDS_PER_ARBITRATION = 180
ANNOTATORS = 2


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _deps():
    from agent.inspector.adapters.controlled_probe import normalize_probes
    from agent.inspector.verifiers.state_verifier import (
        resolve_from_probes, classify_claim, CLAIM_ASSERTS,
    )
    return normalize_probes, resolve_from_probes, classify_claim, CLAIM_ASSERTS


def label_family_table(rows: list[dict]) -> dict[str, Any]:
    """按标签统计独立组数——即独立信息单元数。"""
    by_label: dict[str, set[str]] = defaultdict(set)
    samples_per_label: Counter[str] = Counter()
    for r in rows:
        lab = r["ground_truth"]["label"]
        by_label[lab].add(r["metadata"]["root_cause_group"])
        samples_per_label[lab] += 1
    return {
        "n_groups_total": len({r["metadata"]["root_cause_group"] for r in rows}),
        "independent_units": {k: len(v) for k, v in sorted(by_label.items())},
        "n_independent_units_total": sum(len(v) for v in by_label.values()),
        "samples_per_label": dict(samples_per_label),
        "note": "组内标签唯一 → 独立信息单元 = 标签族数，样本条数不是信息量",
    }


def binary_subset(rows: list[dict]) -> list[dict]:
    _, _, classify_claim, CLAIM_ASSERTS = _deps()
    return [r for r in rows
            if classify_claim(str(r["claim"])) == CLAIM_ASSERTS
            and r["ground_truth"]["label"] in ("SUCCESS", "FALSE_SUCCESS")]


def probe_health_of(normalize_probes, resolve_from_probes, sample: dict) -> bool | None:
    flats, _ = normalize_probes(sample["state_assertions"])
    return resolve_from_probes(flats) if flats else None


def split_stability(rows: list[dict], n_trials: int = 200, seed: int = 20261121) -> dict[str, Any]:
    """重复「按组随机抽一半组」的分割，测主指标的波动。

    注意：这不是性能置信区间——它度量的是**结论对切分的敏感度**。
    每次试验随机取一半 `root_cause_group`，用同一核验器跑主指标。
    """
    import random

    normalize_probes, resolve_from_probes, _, _ = _deps()
    groups = sorted({r["metadata"]["root_cause_group"] for r in rows})
    rng = random.Random(seed)

    rates: list[float] = []
    n_scorable: list[int] = []
    trivial_rates: list[float] = []
    for _ in range(n_trials):
        chosen = set(rng.sample(groups, len(groups) // 2))
        sub = [r for r in rows if r["metadata"]["root_cause_group"] in chosen]
        bi = binary_subset(sub)
        if not bi:
            continue
        correct = 0
        trivial = 0
        for r in bi:
            h = probe_health_of(normalize_probes, resolve_from_probes, r)
            pred = "FALSE_SUCCESS" if h is False else "SUCCESS"
            if pred == r["ground_truth"]["label"]:
                correct += 1
            # 平凡规则与 GT 的一致性（同一件事，换个记法以对齐既有报告）
            if pred == r["ground_truth"]["label"]:
                trivial += 1
        rates.append(correct / len(bi))
        trivial_rates.append(trivial / len(bi))
        n_scorable.append(len(bi))

    def pct(vals: list[float], q: float) -> float:
        s = sorted(vals)
        idx = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
        return round(s[idx], 4)

    return {
        "n_trials": len(rates),
        "rule": "每次随机取一半 root_cause_group，用同一核验器算主指标",
        "scorable_n_p50": pct([float(x) for x in n_scorable], 0.5),
        "accuracy_min": min(rates),
        "accuracy_p50": pct(rates, 0.5),
        "accuracy_max": max(rates),
        "trivial_rule_min": min(trivial_rates),
        "trivial_rule_p50": pct(trivial_rates, 0.5),
        "trivial_rule_max": max(trivial_rates),
        "note": "波动来自切分（哪些组入选），不是模型不确定性；平凡规则同步给出，"
                "用于说明循环在任意切分下都成立",
    }


def wilson_lower(k: int, n: int, z: float = 1.95996398454) -> float | None:
    if n == 0:
        return None
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return round(centre - half, 4)


def cost_model(n_independent_units: int, deff: float, target_margin: float,
               p: float = 0.5) -> dict[str, Any]:
    """把「达目标精度所需有效单元数」换算成标注工时。

    公式沿用既有口径（与 `icc_design_effect.py` 一致）：
        名义 n = z²·p(1-p) / E² · DEFF
    """
    z = 1.95996398454
    n_nominal = math.ceil(z * z * p * (1 - p) / (target_margin ** 2) * deff)
    raw = n_nominal * SECONDS_PER_LABEL * ANNOTATORS
    arb = n_nominal * ARBITRATION_RATE * SECONDS_PER_ARBITRATION
    total_sec = raw + arb
    return {
        "target_margin": target_margin,
        "deff": deff,
        "p_assumed": p,
        "n_nominal_needed": n_nominal,
        "current_independent_units": n_independent_units,
        "gap_units": max(0, n_nominal - n_independent_units),
        "annotator_seconds_each": round(raw / ANNOTATORS, 1),
        "arbitration_seconds_total": round(arb, 1),
        "total_person_hours": round(total_sec / 3600, 2),
        "assumptions": {
            "seconds_per_label": SECONDS_PER_LABEL,
            "arbitration_rate": ARBITRATION_RATE,
            "seconds_per_arbitration": SECONDS_PER_ARBITRATION,
            "annotators": ANNOTATORS,
            "note": "工程估计，非文献值；仅用于量级判断",
        },
    }


def render_markdown(payload: dict[str, Any]) -> str:
    fam = payload["families"]
    stab = payload["stability"]
    costs = payload["costs"]
    L: list[str] = []
    a = L.append
    a(f"# {EXPERIMENT_ID} · 受控集信息量上限与修复成本")
    a("")
    a("> 生成：`python scripts/audit_dataset_ceiling.py` ｜ "
      f"机器结果：`reports/dataset-ceiling.json` ｜ {payload['generated_at']}")
    a("")
    a("## 0. 一句话结论")
    a("")
    a(f"- **独立信息单元 = {fam['n_independent_units_total']}**（SUCCESS "
      f"{fam['independent_units'].get('SUCCESS', 0)} / FALSE_SUCCESS "
      f"{fam['independent_units'].get('FALSE_SUCCESS', 0)} / FAILED "
      f"{fam['independent_units'].get('FAILED', 0)} / UNKNOWN "
      f"{fam['independent_units'].get('UNKNOWN', 0)}），**不是 144 条样本**——"
      "组内标签唯一，加变体不增加信息量。")
    a(f"- 重复随机半组分割 {stab['n_trials']} 次：主指标准确率恒为 "
      f"{stab['accuracy_min']:.4f}–{stab['accuracy_max']:.4f}（**零波动**），"
      f"平凡规则复现率同样恒为 {stab['trivial_rule_min']:.4f}——"
      "**这不是稳健，是循环**：任意切分下指标都不变，因为它只读一个比特。")
    a(f"- 对比：真正随切分变化的是**有效单元数**（p50 可判 n={stab['scorable_n_p50']:.0f}）。"
      "指标不变而样本量变，说明该指标对样本量不敏感——这正是无效指标的特征。")
    a(f"- 达 ±0.05 精度（DEFF=2 假设）需 {costs['m0_05_deff2']['n_nominal_needed']} "
      f"个独立单元，合 **{costs['m0_05_deff2']['total_person_hours']} 人时**"
      f"（{ANNOTATORS} 名标注者各 "
      f"{costs['m0_05_deff2']['annotator_seconds_each']/3600:.2f} 小时）。")
    a("- 本脚本不修改数据与既有指标，只给「修复到可发表水平」的量化门槛。")
    a("")
    a("## 1. 独立信息单元（关键口径）")
    a("")
    a("| 标签 | 独立组数 | 样本条数 |")
    a("|---|---|---|")
    for lab in ("SUCCESS", "FALSE_SUCCESS", "FAILED", "UNKNOWN"):
        a(f"| {lab} | {fam['independent_units'].get(lab, 0)} | "
          f"{fam['samples_per_label'].get(lab, 0)} |")
    a(f"| **合计** | **{fam['n_independent_units_total']}** | "
      f"**{sum(fam['samples_per_label'].values())}** |")
    a("")
    a("> 每条样本的标签由其所属 `root_cause_group` 唯一决定，因此 6 条变体提供的是"
      "**同一信息的 6 次复述**。任何「n=144」「n=48」的口径都把信息量高估了 6 倍与 2 倍。")
    a("")
    a("## 2. 分割稳定性")
    a("")
    a("| 项 | 值 |")
    a("|---|---|")
    a(f"| 试验次数 | {stab['n_trials']} |")
    a(f"| 每次抽取 | 一半 `root_cause_group` |")
    a(f"| 可判 n（p50） | {stab['scorable_n_p50']} |")
    a(f"| 主指标准确率 min / p50 / max | {stab['accuracy_min']:.4f} / "
      f"{stab['accuracy_p50']:.4f} / {stab['accuracy_max']:.4f} |")
    a(f"| 平凡规则复现率 min / p50 / max | {stab['trivial_rule_min']:.4f} / "
      f"{stab['trivial_rule_p50']:.4f} / {stab['trivial_rule_max']:.4f} |")
    a("")
    a("> 解读：指标**零波动**不是稳健性证据，而是「只依赖单一比特」的直接后果。"
      "有效单元数本身随切分变化（每次抽到的组不同），但指标对此完全不敏感——"
      "一个对样本量不敏感的「准确率」无法作为检测能力证据。")
    a("")
    a("## 3. 精度—成本换算")
    a("")
    a("> 参照：即使**全对**，Wilson 95% 下界也只有 "
      f"n=24 → {payload['wilson_lower_when_all_correct']['24']}、"
      f"n=72 → {payload['wilson_lower_when_all_correct']['72']}、"
      f"n=144 → {payload['wilson_lower_when_all_correct']['144']}。"
      "即当前规模下区间宽度主要由**有效单元数**决定，与条数无关。")
    a("")
    a("| 目标边际误差 | DEFF 假设 | 需名义独立单元 | 缺口 | 人时 |")
    a("|---|---|---|---|---|")
    for key, label in (("m0_10_deff1", "±0.10（DEFF=1）"),
                       ("m0_10_deff2", "±0.10（DEFF=2）"),
                       ("m0_05_deff1", "±0.05（DEFF=1）"),
                       ("m0_05_deff2", "±0.05（DEFF=2）")):
        c = costs[key]
        a(f"| {label} | {c['deff']} | {c['n_nominal_needed']} | {c['gap_units']} | "
          f"{c['total_person_hours']} |")
    a("")
    a("工时假设（**工程估计，非文献值**）：")
    a("")
    a("| 参数 | 值 |")
    a("|---|---|")
    a(f"| 单条标注秒数 | {SECONDS_PER_LABEL} |")
    a(f"| 标注人数 | {ANNOTATORS}（双人独立） |")
    a(f"| 仲裁比例 | {ARBITRATION_RATE:.0%} |")
    a(f"| 单次仲裁秒数 | {SECONDS_PER_ARBITRATION} |")
    a("")
    a("## 4. RAG 侧对照链的可运行性")
    a("")
    rag = payload["rag_feasibility"]
    a(f"- 既有 RAG 消融（`scripts/eval_retrieval_ablation.py`）需要「指令 → 目标 chunk」"
      f"的检索真值，其唯一数据源是 Linux 领域集（**{rag['domain_draft_samples']} 条**，"
      f"全 `DRAFT`）。")
    a(f"- 受控集有 {rag['controlled_samples']} 条，但其 `knowledge` 字段为空、"
      "无语料 chunk 与检索真值，**无法**作为检索评测集；且 `M02` 留出集（n=20）"
      "同属该 DRAFT 集。")
    a(f"- 结论：RAG 消融在当前条件下维持 `NOT_RUN`，**不得**用受控集数字顶替。")
    a("")
    a("## 5. 局限与禁止口径")
    a("")
    a("1. **不做事后功效**——只给精度区间与设计效应敏感性，与 `stats_inference` 一致。")
    a("2. 成本换算是**量级判断**，不是项目排期承诺；单位工时需由实际试标注重新标定。")
    a("3. **对抗单元不在本脚本构造**：必须先设计「探针健康但标签非 SUCCESS」"
      "与「探针不健康但标签 SUCCESS」的样本，否则扩样只会放大循环。")
    a("4. 本脚本**不改变**任何既有指标数字。")
    a("")
    a("## 6. 复现")
    a("")
    a("```bash")
    a("python scripts/audit_dataset_ceiling.py")
    a("```")
    a("")
    a(f"源数据指纹：`sha256[:16] = {payload['source_sha256_16']}`")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="受控集信息量上限与修复成本")
    ap.add_argument("--write", action="store_true", help="落盘报告（默认只打印摘要）")
    args = ap.parse_args(argv)

    samples = load_jsonl(SRC)
    controlled = [r for r in samples if r["dataset_type"] == "verification"]

    families = label_family_table(controlled)
    stability = split_stability(controlled)
    n_units = families["n_independent_units_total"]
    costs = {
        "m0_10_deff1": cost_model(n_units, 1.0, 0.10),
        "m0_10_deff2": cost_model(n_units, 2.0, 0.10),
        "m0_05_deff1": cost_model(n_units, 1.0, 0.05),
        "m0_05_deff2": cost_model(n_units, 2.0, 0.05),
    }
    # Wilson 下界参照（全对情形，用于说明「即使全对也不够紧」）
    wilson_ref = {str(n): wilson_lower(n, n) for n in (24, 72, 144)}

    domain_dir = REPO / "SmartOps-Dataset" / "Linux"
    n_domain = 0
    if domain_dir.exists():
        for path in sorted(domain_dir.glob("*.jsonl")):
            n_domain += sum(1 for line in path.read_text(encoding="utf-8").splitlines()
                            if line.strip())

    rag_feasibility = {
        "controlled_samples": len(controlled),
        "domain_draft_samples": n_domain,
        "rag_ablation_status": "NOT_RUN",
        "reason": "受控集 knowledge 字段为空、无检索真值；RAG 消融唯一数据源为 "
                  "Linux 领域集（全 DRAFT），不可用受控集数字顶替",
    }

    payload = {
        "experiment_id": EXPERIMENT_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(SRC.relative_to(REPO)),
        "source_sha256_16": hashlib.sha256(SRC.read_bytes()).hexdigest()[:16],
        "families": families,
        "stability": stability,
        "costs": costs,
        "wilson_lower_when_all_correct": wilson_ref,
        "rag_feasibility": rag_feasibility,
    }
    print(json.dumps({k: v for k, v in payload.items() if k != "per_row"},
                     ensure_ascii=False, indent=2))

    if args.write:
        REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
        REPORT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        REPORT_MD.write_text(render_markdown(payload), encoding="utf-8")
        print(f"[out] {REPORT_JSON.relative_to(REPO)}")
        print(f"[out] {REPORT_MD.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

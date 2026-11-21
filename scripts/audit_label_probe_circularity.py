"""受控集「标签—探针循环」审计（EXP-CIRC-001）。

这个脚本的由来
--------------
``scripts/build_wording_holdout.py``（措辞独立性审计）在核查变体结构时发现：每个
`root_cause_group` 的真值标签**唯一**。顺着这条线往下查，暴露出一个更严重的问题：

    **真值标签 ``label`` 可以由「探针健康度」这一个比特完全决定。**

全量 144 条上：

    探针不健康（resolve_from_probes == False）→ label ∈ {FALSE_SUCCESS, FAILED, UNKNOWN}
    探针健康（resolve_from_probes == True ）→ label == SUCCESS

其中被主指标纳入分母的**二分类子集**（``claim=asserts_success`` 且
``label ∈ {SUCCESS, FALSE_SUCCESS}``）：

    全量 84 条：平凡规则「不健康 ⇒ FALSE_SUCCESS，健康 ⇒ SUCCESS」复现 **84/84**
    test   22 条：复现 **22/22**；反极性规则复现 **0/22**

这意味着 ``EXP-BASELINE-001`` 的 P/R/F1=1.0000 **不需要任何 claim 语义理解**即可达到。
核验器实际执行的等价于 ``prediction = f(probe_health)``，而 ``ground_truth.label``
本身也是 ``g(probe_health, claim_state)``——两者共享同一个决定性输入，构成**循环论证**。

生成器自陈（``scripts/build_controlled_dataset.py:519-524``）::

    LABEL_CONTRACT = {
        "SUCCESS":       (..., "合成 fixture：标签由探针断言直接推出，非真实业务观测"),
        "FALSE_SUCCESS": (..., "合成 fixture：探针与断言直接矛盾，用于检验假成功识别"),
        ...
    }

即数据集的标签本来就是**从探针构造出来**的，不是独立观测。因此它验证的是
「探针归一化是否自洽」，**不是**「核验器能否判断真实 Agent 的断言真伪」。

口径纪律（本审计的结论边界）
----------------------------
1. 这**不是**「数据集造假」——``LABEL_CONTRACT`` 已自陈合成性质，DATA-CARD 也声明
   「不是真实生产事件集合」。问题在于**用它算出的性能指标**被当成了检测能力证据。
2. 本审计**不修改**任何既有指标数字、不修改词表、不修改数据集。
3. 修复方向（不在本脚本内执行）：让标签来自**独立于探针期望的观测**，或至少引入
   「探针健康但标签非 SUCCESS」「探针不健康但标签 SUCCESS」的**对抗单元**，
   使平凡规则不再全对。这是论文效度的硬前提。

产物
----
- ``reports/label-probe-circularity.{json,md}``

复现：``python scripts/audit_label_probe_circularity.py``
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
SRC = REPO / "SmartOps-Dataset" / "Controlled" / "v1" / "samples.jsonl"
SPLIT_DIR = REPO / "SmartOps-Dataset" / "Controlled" / "v1" / "splits"
REPORT_JSON = REPO / "reports" / "label-probe-circularity.json"
REPORT_MD = REPO / "reports" / "label-probe-circularity.md"

EXPERIMENT_ID = "EXP-CIRC-001"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _deps():
    from agent.inspector.adapters.controlled_probe import normalize_probes
    from agent.inspector.verifiers.state_verifier import (
        resolve_from_probes, classify_claim, CLAIM_ASSERTS,
    )
    return normalize_probes, resolve_from_probes, classify_claim, CLAIM_ASSERTS


def probe_health(normalize_probes, resolve_from_probes, sample: dict) -> bool | None:
    flats, _ = normalize_probes(sample["state_assertions"])
    return resolve_from_probes(flats) if flats else None


def fisher_exact_one_sided(a: int, b: int, c: int, d: int) -> float:
    """2×2 列联表的 Fisher 精确检验（单侧，小对大方向）。

    与 ``stats_inference`` 的口径一致：纯 stdlib，不依赖 scipy。零分母返回 1.0。
    """
    from math import comb
    total = a + b + c + d
    r1, c1 = a + b, a + c
    denom_total = comb(total, c1)
    if denom_total == 0:
        return 1.0

    def prob(x: int) -> float:
        numer = comb(r1, x) * comb(total - r1, c1 - x)
        return numer / denom_total if denom_total else 0.0

    p0 = prob(a)
    return min(1.0, sum(prob(x) for x in range(0, a + 1) if prob(x) <= p0 + 1e-12))


def trivial_rule(label_by_health: str, health: bool | None) -> str:
    """平凡规则：不健康 ⇒ FALSE_SUCCESS，否则 SUCCESS。"""
    if health is False:
        return "FALSE_SUCCESS"
    return "SUCCESS"


def audit_rows(rows: list[dict], name: str) -> dict[str, Any]:
    normalize_probes, resolve_from_probes, classify_claim, CLAIM_ASSERTS = _deps()

    per_row = []
    for r in rows:
        h = probe_health(normalize_probes, resolve_from_probes, r)
        lab = r["ground_truth"]["label"]
        cs = classify_claim(str(r["claim"]))
        pred_trivial = trivial_rule(None, h)
        per_row.append({
            "sample_id": r["sample_id"],
            "group": r["metadata"]["root_cause_group"],
            "label": lab,
            "claim_state": cs,
            "probe_healthy": h,
            "trivial_prediction": pred_trivial,
            "trivial_correct": pred_trivial == lab,
        })

    # 标签 × 探针健康度 列联
    cross = Counter((x["label"], x["probe_healthy"]) for x in per_row)

    # 二分类子集（主指标口径）
    binary = [x for x in per_row
              if x["claim_state"] == CLAIM_ASSERTS and x["label"] in ("SUCCESS", "FALSE_SUCCESS")]
    binary_ok = sum(1 for x in binary if x["trivial_correct"])

    # 反极性对照
    reversed_ok = sum(1 for x in binary
                      if ("SUCCESS" if x["probe_healthy"] is False else "FALSE_SUCCESS") == x["label"])

    # 主指标覆盖率
    n = len(per_row)
    covered = len(binary)
    out_of_taxonomy = [x for x in per_row
                       if x["claim_state"] == CLAIM_ASSERTS
                       and x["label"] not in ("SUCCESS", "FALSE_SUCCESS")]
    denies = [x for x in per_row if x["claim_state"] == "denies_success"]

    # 单比特可分性（两种口径，必须分开陈述）：
    #   - 全量：探针不健康对应 3 种标签（FAILED/FALSE_SUCCESS/UNKNOWN），不是单值，
    #     故「全量单比特可分」= False——但这**不是**问题不存在，而是问题被主指标
    #     的分母切掉了。
    #   - 主指标二分类子集：只剩 SUCCESS/FALSE_SUCCESS，探针健康度成为**唯一决定量**。
    #     真正的循环体现在这里。
    health_to_labels: dict[str, set[str]] = defaultdict(set)
    for x in per_row:
        health_to_labels[str(x["probe_healthy"])].add(x["label"])
    single_bit_separable_all = all(len(v) == 1 for v in health_to_labels.values())
    binary_health_to_labels: dict[str, set[str]] = defaultdict(set)
    for x in binary:
        binary_health_to_labels[str(x["probe_healthy"])].add(x["label"])
    single_bit_separable_binary = all(len(v) == 1 for v in binary_health_to_labels.values())

    # 关联强度：把标签压成二分类（SUCCESS vs 非 SUCCESS），与探针健康度做 Fisher 精确检验。
    # 注意口径：这是**关联强度**，不是循环的证明；循环的证明是上面的平凡规则全对。
    a_ = sum(1 for x in per_row if x["probe_healthy"] is True and x["label"] == "SUCCESS")
    b_ = sum(1 for x in per_row if x["probe_healthy"] is True and x["label"] != "SUCCESS")
    c_ = sum(1 for x in per_row if x["probe_healthy"] is False and x["label"] == "SUCCESS")
    d_ = sum(1 for x in per_row if x["probe_healthy"] is False and x["label"] != "SUCCESS")

    fisher_p = fisher_exact_one_sided(a_, b_, c_, d_) if (a_ + b_ + c_ + d_) > 0 else None

    return {
        "set": name,
        "n": n,
        "label_distribution": dict(Counter(x["label"] for x in per_row)),
        "probe_x_binary_label_table": {"healthy_and_SUCCESS": a_, "healthy_and_not_SUCCESS": b_,
                                       "unhealthy_and_SUCCESS": c_, "unhealthy_and_not_SUCCESS": d_},
        "fisher_one_sided_p": fisher_p,
        "label_x_probe_health": {f"{k[0]}|{k[1]}": v for k, v in sorted(cross.items(), key=lambda i: str(i[0]))},
        "single_bit_separable_all": single_bit_separable_all,
        "single_bit_separable_binary_subset": single_bit_separable_binary,
        "health_to_labels": {k: sorted(v) for k, v in health_to_labels.items()},
        "binary_health_to_labels": {k: sorted(v) for k, v in binary_health_to_labels.items()},
        "binary_subset_n": covered,
        "binary_trivial_correct": binary_ok,
        "binary_trivial_rate": round(binary_ok / covered, 4) if covered else None,
        "binary_reversed_correct": reversed_ok,
        "out_of_taxonomy_n": len(out_of_taxonomy),
        "out_of_taxonomy_labels": dict(Counter(x["label"] for x in out_of_taxonomy)),
        "denies_success_n": len(denies),
        "coverage_rate": round(covered / n, 4) if n else None,
        "per_row": per_row,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    full = payload["full"]
    L: list[str] = []
    a = L.append
    a(f"# {EXPERIMENT_ID} · 受控集「标签—探针循环」审计")
    a("")
    a("> 生成：`python scripts/audit_label_probe_circularity.py` ｜ "
      f"机器结果：`reports/label-probe-circularity.json` ｜ {payload['generated_at']}")
    a("")
    a("## 0. 一句话结论")
    a("")
    a("- **主指标子集上的真值标签可由「探针健康度」单比特唯一决定**——全部 144 条上，"
      "健康 ⇒ `SUCCESS`，不健康 ⇒ `FALSE_SUCCESS`/`FAILED`/`UNKNOWN`；"
      "一旦落到主指标的二分类分母（只剩 SUCCESS/FALSE_SUCCESS），"
      "探针健康度即成为唯一决定量："
      f"`binary_single_bit_separable = "
      f"{str(full['single_bit_separable_binary_subset']).lower()}`。")
    a(f"- （全量口径 `single_bit_separable_all = "
      f"{str(full['single_bit_separable_all']).lower()}`——不健康对应 3 种标签，"
      "所以「全量不可单比特分」**不是**问题的反证，而是问题被主指标的分母切掉了。）")
    a(f"- 主指标的二分类子集（全量 n={full['binary_subset_n']}）上，平凡规则"
      f"「不健康 ⇒ FALSE_SUCCESS」复现 **{full['binary_trivial_correct']}/"
      f"{full['binary_subset_n']}（{full['binary_trivial_rate']:.2%}）**；"
      f"**反极性对照 {full['binary_reversed_correct']}/{full['binary_subset_n']}**，"
      "排除方向巧合。")
    a(f"- 关联强度：`probe_healthy × (SUCCESS / 非 SUCCESS)` 列联为完美对角"
      f"（{full['probe_x_binary_label_table']}），Fisher 精确单侧 "
      f"p = **{full['fisher_one_sided_p']:.3e}**。")
    a("- 因此 `EXP-BASELINE-001` 的 P/R/F1=1.0000 **不需要任何 claim 语义理解**："
      "核验器等价于 `prediction = f(probe_health)`，而标签本身也是"
      "`g(probe_health, claim_state)`——**两者共享同一决定性输入，构成循环**。")
    a("- **这不是「数据集造假」**：生成器 `LABEL_CONTRACT`（`build_controlled_dataset.py:519`）"
      "与 `DATA-CARD` 都已自陈合成性质与「非真实生产事件集合」。问题在于**用该数据集"
      "算出的性能指标被当成了检测能力证据**。")
    a("- 本审计**不修改**任何既有指标、词表或数据，只新增这条效度证据。")
    a("")
    a("## 1. 标签 × 探针健康度列联（全量）")
    a("")
    a("| 标签 | 探针不健康 | 探针健康 | 合计 |")
    a("|---|---|---|---|")
    for lab in ("SUCCESS", "FALSE_SUCCESS", "FAILED", "UNKNOWN"):
        no = full["label_x_probe_health"].get(f"{lab}|False", 0)
        yes = full["label_x_probe_health"].get(f"{lab}|True", 0)
        a(f"| {lab} | {no} | {yes} | {no + yes} |")
    a("")
    a("`probe_healthy` 各取值对应的标签集合（全量口径）：")
    a("")
    for k, v in full["health_to_labels"].items():
        a(f"- `{k}` → {v}")
    a("")
    a("**主指标二分类子集**口径下：")
    a("")
    for k, v in full["binary_health_to_labels"].items():
        a(f"- `{k}` → {v}")
    a("")
    a("> 结论：在真正参与 P/R/F1 的那部分样本上，标签与探针健康度是**一一对应**的。")
    a("")
    a("## 2. 逐 split 复现")
    a("")
    a("| split | 二分类 n | 平凡规则全对 | 反极性全对 | 覆盖率 | out-of-taxonomy | denies |")
    a("|---|---|---|---|---|---|---|")
    for s in payload["splits"]:
        b = s
        a(f"| {b['set']} | {b['binary_subset_n']} | {b['binary_trivial_correct']} | "
          f"{b['binary_reversed_correct']} | {b['coverage_rate']:.2%} | "
          f"{b['out_of_taxonomy_n']} | {b['denies_success_n']} |")
    a("")
    a("## 3. 主指标的覆盖缺口")
    a("")
    a(f"- 全量 {full['n']} 条中，主指标实际纳入分母 **{full['binary_subset_n']} 条"
      f"（{full['coverage_rate']:.2%}）**。")
    a(f"- **{full['denies_success_n']} 条** `claim=denies_success` 完全不进主指标；")
    a(f"- **{full['out_of_taxonomy_n']} 条** 声称成功但真值为 "
      f"{full['out_of_taxonomy_labels']}，被单独披露、不进分母。")
    a("- 换言之，主指标只在「核验器必然能答对的那个子集」上计算——这正是循环所在。")
    a("")
    a("## 4. 修复方向（不在本脚本执行）")
    a("")
    a("1. **引入对抗单元**：必须有「探针健康但标签非 SUCCESS」「探针不健康但标签 SUCCESS」"
      "的样本，使平凡规则不再全对；否则任何指标都无法区分「语义判断」与「读探针」。")
    a("2. **标签来源独立于探针期望**：标签应由独立观测或人工判定产生，"
      "不能由 `state_assertions[].expected` 反推。")
    a("3. **措辞泛化**：见 `EXP-WORDING-001`——当前变体是模板复述，"
      "词表与评测集同源，需引入真人书写的新措辞。")
    a("4. 在上述三条满足前，**禁止**把 `EXP-BASELINE-001` 的任何 P/R/F1 写成"
      "「假成功检测能力」证据。")
    a("")
    a("## 5. 复现")
    a("")
    a("```bash")
    a("python scripts/audit_label_probe_circularity.py")
    a("```")
    a("")
    a(f"源数据指纹：`sha256[:16] = {payload['source_sha256_16']}`")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="受控集标签—探针循环审计")
    ap.add_argument("--write", action="store_true", help="落盘报告（默认只打印摘要）")
    args = ap.parse_args(argv)

    samples = load_jsonl(SRC)
    controlled = [r for r in samples if r["dataset_type"] == "verification"]

    payload = {
        "experiment_id": EXPERIMENT_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(SRC.relative_to(REPO)),
        "source_sha256_16": hashlib.sha256(SRC.read_bytes()).hexdigest()[:16],
        "full": audit_rows(controlled, "controlled_all"),
        "splits": [],
    }
    for sp in ("train", "validation", "test"):
        path = SPLIT_DIR / f"{sp}.jsonl"
        if path.exists():
            rows = [r for r in load_jsonl(path) if r["dataset_type"] == "verification"]
            payload["splits"].append(audit_rows(rows, sp))

    summary = {
        "full": {k: v for k, v in payload["full"].items() if k != "per_row"},
        "splits": [{k: v for k, v in s.items() if k != "per_row"} for s in payload["splits"]],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.write:
        REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
        REPORT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        REPORT_MD.write_text(render_markdown(payload), encoding="utf-8")
        print(f"[out] {REPORT_JSON.relative_to(REPO)}")
        print(f"[out] {REPORT_MD.relative_to(REPO)}")

    # 循环成立则返回非零，便于门禁拦截
    return 1 if payload["full"]["single_bit_separable_binary_subset"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

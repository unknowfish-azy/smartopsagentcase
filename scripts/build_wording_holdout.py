"""受控集变体结构与措辞独立性审计（EXP-WORDING-001）。

这个脚本最初的设想是「措辞层留出集」——把一部分 claim 切到留出侧，检验核验器是否
只是记住了模板串。**实跑后发现该设想在本数据集上不成立**，原因见下，本脚本因此
改为**审计**，并把发现作为结论输出。

为什么措辞留出不可行（实测）
----------------------------
24 个 `root_cause_group`，每组的构成为 **2 个场景 × 3 条 claim 模板**，
组内唯一模板串只有 3–6 条（15 组 6 条、6 组 5 条、2 组 4 条、1 组 3 条）。
按「前 3 条进 held、后 3 条进 dev」切分后，两侧仍有 **13 条 claim 精确重叠**
（如「主从同步正常了」「redis 缓存可用」「配置已生效」）——因为这些短模板在两个
场景里被重复使用。长度 ≥8 的公共片段多达 645 个。

**结论（不是失败，是数据集的性质）**：受控集的 6 条变体是**同一批模板的复述**
（换主机名/路径），不是独立措辞样本。因此：

- 任何「在受控集上 P/R/F1=1.0」的结果，其措辞泛化性**未被检验**；
- 词表本身取自这 144 条真实 claim（`state_verifier.py` L76–145 的覆盖清单），
  与评测集同源，存在**循环**；
- 要检验措辞泛化，必须引入**新的措辞来源**（真人书写 / 另一生成器），
  这不是切分能解决的。

本脚本产出的三个可引用量
------------------------
1. **变体结构**：每组场景数、唯一模板串数、跨场景复用度。
2. **措辞隔离校验**：切分后精确重叠数与公共片段数（证明留出不可行）。
3. **同组配对一致性**：对每个 `root_cause_group`，比较它在两侧的判定是否一致
   （单位=组，因组内标签唯一）。这是本数据集能给出的最强对照。

口径纪律
--------
- 本脚本**不修改词表**、不修改既有任何指标。
- 「同组配对一致性 100%」**不等于**措辞泛化已验证——只说明同模板复述下判定稳定。
- 全部为合成 fixture、`approved=False`。

产物
----
- ``reports/wording-holdout.{json,md}``

复现：``python scripts/build_wording_holdout.py``
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
SRC = REPO / "SmartOps-Dataset" / "Controlled" / "v1" / "samples.jsonl"
SPLIT_DIR = REPO / "SmartOps-Dataset" / "Controlled" / "v1" / "splits"
REPORT_JSON = REPO / "reports" / "wording-holdout.json"
REPORT_MD = REPO / "reports" / "wording-holdout.md"

EXPERIMENT_ID = "EXP-WORDING-001"
HELD_VARIANTS_PER_GROUP = 3


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def normalize(text: str) -> str:
    """与 ``classify_claim`` 同款归一化：小写 + 折叠连续空白。"""
    return " ".join(text.lower().split())


def group_structure(rows: list[dict]) -> dict[str, Any]:
    """每组的场景数、唯一模板数、跨场景复用度。"""
    per_group: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["dataset_type"] == "verification":
            per_group[r["metadata"]["root_cause_group"]].append(r)

    detail: dict[str, Any] = {}
    tmpl_counts: Counter[int] = Counter()
    scen_counts: Counter[int] = Counter()
    reuse_rates: list[float] = []
    for key in sorted(per_group):
        rs = per_group[key]
        by_scen: dict[str, set[str]] = defaultdict(set)
        for r in rs:
            by_scen[r["metadata"]["scenario_id"]].add(normalize(str(r["claim"])))
        n_scen = len(by_scen)
        all_tmpl = set().union(*by_scen.values()) if by_scen else set()
        # 复用度：至少出现在 2 个场景里的模板占比
        repeated = sum(1 for t in all_tmpl if sum(t in s for s in by_scen.values()) >= 2)
        rate = (repeated / len(all_tmpl)) if all_tmpl else 0.0
        reuse_rates.append(rate)
        tmpl_counts[len(all_tmpl)] += 1
        scen_counts[n_scen] += 1
        detail[key] = {
            "n_samples": len(rs),
            "n_scenarios": n_scen,
            "n_unique_claims": len(all_tmpl),
            "n_repeated_across_scenarios": repeated,
            "reuse_rate": round(rate, 4),
            "label": rs[0]["ground_truth"]["label"],
            "family": rs[0]["metadata"]["family"],
        }
    return {
        "n_groups": len(per_group),
        "n_scenarios_per_group": dict(sorted(scen_counts.items())),
        "n_unique_claims_per_group": dict(sorted(tmpl_counts.items())),
        "mean_reuse_rate": round(sum(reuse_rates) / len(reuse_rates), 4) if reuse_rates else None,
        "groups": detail,
    }


def isolation_check(held: list[dict], dev: list[dict]) -> dict[str, Any]:
    """切分后测措辞重叠，用于证明「措辞留出不可行」。"""
    def claims(rows: list[dict]) -> set[str]:
        return {normalize(str(r["claim"])) for r in rows} - {""}

    held_c, dev_c = claims(held), claims(dev)
    overlap = sorted(held_c & dev_c)

    def frags(text: str, min_len: int = 8) -> set[str]:
        chars = [c for c in text if not c.isspace()]
        out: set[str] = set()
        n = len(chars)
        for i in range(n):
            for j in range(i + min_len, min(n, i + 20) + 1):
                out.add("".join(chars[i:j]))
        return out

    dev_frags: set[str] = set()
    for t in dev_c:
        dev_frags |= frags(t)
    shared = sorted({f for t in held_c for f in frags(t)} & dev_frags)

    return {
        "rule": f"每 group 按 sample_id 升序取前 {HELD_VARIANTS_PER_GROUP} 条进 held",
        "n_held_unique_claims": len(held_c),
        "n_dev_unique_claims": len(dev_c),
        "exact_overlap_count": len(overlap),
        "exact_overlap": overlap,
        "shared_fragment_count_ge8": len(shared),
        "shared_fragment_sample": shared[:10],
        "wording_holdout_feasible": len(overlap) == 0,
    }


_BASELINE_MODULE = None


def _baseline():
    global _BASELINE_MODULE
    if _BASELINE_MODULE is None:
        import importlib.util
        path = REPO / "scripts" / "eval_controlled_baseline.py"
        spec = importlib.util.spec_from_file_location("eval_controlled_baseline", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["eval_controlled_baseline"] = module
        spec.loader.exec_module(module)
        _BASELINE_MODULE = module
    return _BASELINE_MODULE


def side_metrics(name: str, rows: list[dict]) -> dict[str, Any]:
    block = _baseline().evaluate_split(name, rows)
    m = block["primary_metrics_scorable_subset"]
    return {
        "side": name,
        "n_rows": len(rows),
        "scorable_n": m["scorable_n"],
        "scorable_binary_n": m["scorable_binary_n"],
        "out_of_taxonomy_n": m["out_of_taxonomy_n"],
        "TP": m["TP"], "TN": m["TN"], "FP": m["FP"], "FN": m["FN"],
        "precision": m["precision"]["value"],
        "recall": m["recall"]["value"],
        "F1": m["F1"],
        "accuracy": m["accuracy"]["value"],
        "uncertain_rate": m["uncertain_rate"]["value"],
        "rows": [{"sample_id": r["sample_id"], "family": r.get("family"),
                  "ground_truth": r["ground_truth"], "prediction": r["prediction"],
                  "claim_state": r["claim_state"], "probe_healthy": r.get("probe_healthy")}
                 for r in block["rows"]],
    }


def group_paired_consistency(dev: dict, held: dict, group_of: dict[str, str],
                             group_label: dict[str, str]) -> dict[str, Any]:
    """以 `root_cause_group` 为单位比较两侧判定是否全对。

    两侧的样本不是同一条（一条在 held、一条在 dev），但**同属一个组**，而组内标签
    唯一、有效信息量以组数计，所以**组**是本数据集能提供的最小可比单位。
    """
    def by_group(rows: list[dict]) -> dict[str, bool]:
        out: dict[str, bool] = {}
        for r in rows:
            g = group_of.get(r["sample_id"])
            if g is None:
                continue
            ok = r["ground_truth"] == r["prediction"]
            out[g] = out.get(g, True) and ok
        return out

    d, h = by_group(dev["rows"]), by_group(held["rows"])
    common = sorted(set(d) & set(h))
    both_ok = [g for g in common if d[g] and h[g]]
    only_dev = [g for g in common if d[g] and not h[g]]
    only_held = [g for g in common if h[g] and not d[g]]
    both_bad = [g for g in common if not d[g] and not h[g]]
    return {
        "unit": "root_cause_group",
        "n_groups": len(common),
        "both_all_correct": len(both_ok),
        "only_dev_correct": only_dev,
        "only_held_correct": only_held,
        "both_incorrect": both_bad,
        "agreement_rate": round(len(both_ok) / len(common), 4) if common else None,
        "per_group": [{"group": g, "label": group_label.get(g),
                       "dev_all_correct": d[g], "held_all_correct": h[g]} for g in common],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    st = payload["structure"]
    iso = payload["isolation"]
    sides = payload["sides"]
    gp = payload["group_paired"]
    L: list[str] = []
    a = L.append
    a(f"# {EXPERIMENT_ID} · 受控集变体结构与措辞独立性审计")
    a("")
    a("> 生成：`python scripts/build_wording_holdout.py` ｜ "
      f"机器结果：`reports/wording-holdout.json` ｜ {payload['generated_at']}")
    a("")
    a("## 0. 一句话结论")
    a("")
    a(f"- **「措辞层留出集」在本数据集上不可行**：24 组每组仅 "
      f"{st['n_scenarios_per_group']} 个场景，唯一 claim 串只有 "
      f"{min(st['n_unique_claims_per_group'])}–{max(st['n_unique_claims_per_group'])} 条/组，"
      f"跨场景模板复用率均值 **{st['mean_reuse_rate']:.2%}**。")
    a(f"- 强行按变体切开后，两侧仍有 **{iso['exact_overlap_count']} 条 claim 精确重叠**、"
      f"{iso['shared_fragment_count_ge8']} 个 ≥8 字符公共片段 → "
      f"`wording_holdout_feasible = {str(iso['wording_holdout_feasible']).lower()}`。")
    a("- **这意味着什么**：受控集的 6 条变体是**同一批模板的复述**（换主机名/路径），"
      "不是独立措辞样本；而成功断言词表正是从这 144 条 claim 中挑出的短语，"
      "**词表与评测集同源**。因此受控集上的指标只能说明「模板内判定稳定」，"
      "**不能**证明措辞泛化。")
    a(f"- 同组配对一致性（单位=组，n={gp['n_groups']}）：**{gp['both_all_correct']} 组两侧全对**"
      f"（{gp['agreement_rate']:.2%}）；仅 dev 全对 "
      f"{len(gp['only_dev_correct'])} 组、仅 held 全对 {len(gp['only_held_correct'])} 组、"
      f"两侧均有错 {len(gp['both_incorrect'])} 组。")
    a("- **本审计不修改词表、不修改任何既有指标**，只新增这条泛化边界证据。")
    a("")
    a("## 1. 变体结构（为什么留出不可行）")
    a("")
    a("| 项 | 值 |")
    a("|---|---|")
    a(f"| 受控组数 | {st['n_groups']} |")
    a(f"| 每组场景数分布 | {st['n_scenarios_per_group']} |")
    a(f"| 每组唯一 claim 串数分布 | {st['n_unique_claims_per_group']} |")
    a(f"| 跨场景模板复用率均值 | {st['mean_reuse_rate']:.2%} |")
    a("")
    a("| 组 | 族 | 标签 | 样本 | 场景 | 唯一 claim | 跨场景复用 | 复用率 |")
    a("|---|---|---|---|---|---|---|---|")
    for k, v in st["groups"].items():
        a(f"| {k} | {v['family']} | {v['label']} | {v['n_samples']} | "
          f"{v['n_scenarios']} | {v['n_unique_claims']} | "
          f"{v['n_repeated_across_scenarios']} | {v['reuse_rate']:.2%} |")
    a("")
    a("## 2. 措辞隔离校验（切分负对照）")
    a("")
    a("| 项 | 值 |")
    a("|---|---|")
    a(f"| 切分规则 | `{iso['rule']}` |")
    a(f"| held 侧唯一 claim | {iso['n_held_unique_claims']} |")
    a(f"| dev 侧唯一 claim | {iso['n_dev_unique_claims']} |")
    a(f"| **精确重叠** | **{iso['exact_overlap_count']}** |")
    a(f"| ≥8 字符公共片段 | {iso['shared_fragment_count_ge8']} |")
    a(f"| 措辞留出可行 | {iso['wording_holdout_feasible']} |")
    a("")
    a("精确重叠的 claim 串（这些串在两侧都出现，故任何按变体的切分都无法隔离措辞）：")
    a("")
    for s in iso["exact_overlap"]:
        a(f"- `{s}`")
    a("")
    a("> 解读：重叠不是「切分没做好」，而是**数据集构造方式**决定的——"
      "生成器用 3 条模板 × 2 场景铺满 6 个变体，短模板必然跨场景复用。"
      "这不是可以靠换切分种子修掉的问题。")
    a("")
    a("## 3. 两侧指标（同分布不同变体）")
    a("")
    a("| 侧 | 可判 n | 二分类 n | TP | TN | FP | FN | P | R | F1 | 准确率 | uncertain 率 |")
    a("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for name in ("dev", "held"):
        b = sides[name]
        a(f"| {name} | {b['scorable_n']} | {b['scorable_binary_n']} | "
          f"{b['TP']} | {b['TN']} | {b['FP']} | {b['FN']} | "
          f"{b['precision']:.4f} | {b['recall']:.4f} | {b['F1']:.4f} | "
          f"{b['accuracy']:.4f} | {b['uncertain_rate']:.4f} |")
    a("")
    a("> 两侧指标相同**不构成泛化证据**：两侧共享同一批模板串（§2），"
      "这是「同模板复述下判定稳定」的重复验证。")
    a("")
    a("## 4. 同组配对一致性")
    a("")
    a("| 项 | 值 |")
    a("|---|---|")
    a(f"| 配对单位 | `root_cause_group`（组内标签唯一，组是最小可比单位） |")
    a(f"| 组数 | {gp['n_groups']} |")
    a(f"| 两侧均全对 | {gp['both_all_correct']} |")
    a(f"| 仅 dev 全对 | {len(gp['only_dev_correct'])} |")
    a(f"| 仅 held 全对 | {len(gp['only_held_correct'])} |")
    a(f"| 两侧均有错 | {len(gp['both_incorrect'])} |")
    a(f"| 一致率 | {gp['agreement_rate']} |")
    a("")
    a("| 组 | 标签 | dev 全对 | held 全对 |")
    a("|---|---|---|---|")
    for g in gp["per_group"]:
        a(f"| {g['group']} | {g['label']} | {g['dev_all_correct']} | {g['held_all_correct']} |")
    a("")
    a("## 5. 局限与禁止口径")
    a("")
    a("1. **不得**把「同组配对一致率 100%」写成「措辞泛化已验证」——"
      "两侧共享模板串，这是模板内稳定性，不是跨措辞泛化。")
    a("2. **不得**用 ICC=1.0000 或本审计的任何数字宣称性能；全部为合成 fixture、"
      "`approved=False`、核验器为确定性规则而非 LLM。")
    a("3. **要真正检验措辞泛化**，必须引入**新措辞来源**：①2 名以上真人按同一探针"
      "手写断言；②另一个独立生成器（不同模板池）重新生成。这是本项剩下的唯一外部条件。")
    a("4. 本审计**不改变** M20/M26/M27 的任何数字，只增加泛化边界证据。")
    a("")
    a("## 6. 复现")
    a("")
    a("```bash")
    a("python scripts/build_wording_holdout.py")
    a("```")
    a("")
    a(f"源数据指纹：`sha256[:16] = {payload['source_sha256_16']}`")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="受控集变体结构与措辞独立性审计")
    ap.add_argument("--write", action="store_true", help="落盘报告（默认只打印摘要）")
    args = ap.parse_args(argv)

    samples = load_jsonl(SRC)
    structure = group_structure(samples)

    per_group: dict[str, list[dict]] = defaultdict(list)
    for s in samples:
        if s["dataset_type"] == "verification":
            per_group[s["metadata"]["root_cause_group"]].append(s)
    held: list[dict] = []
    dev: list[dict] = []
    for key in sorted(per_group):
        rows = sorted(per_group[key], key=lambda r: r["sample_id"])
        held.extend(rows[:HELD_VARIANTS_PER_GROUP])
        dev.extend(rows[HELD_VARIANTS_PER_GROUP:])

    isolation = isolation_check(held, dev)
    sides = {"dev": side_metrics("wording_dev", dev),
             "held": side_metrics("wording_held", held)}

    group_of = {r["sample_id"]: r["metadata"]["root_cause_group"] for r in held + dev}
    group_label = {r["metadata"]["root_cause_group"]: r["ground_truth"]["label"]
                   for r in held + dev}
    paired = group_paired_consistency(sides["dev"], sides["held"], group_of, group_label)

    payload = {
        "experiment_id": EXPERIMENT_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(SRC.relative_to(REPO)),
        "source_sha256_16": hashlib.sha256(SRC.read_bytes()).hexdigest()[:16],
        "structure": structure,
        "isolation": isolation,
        "sides": sides,
        "group_paired": paired,
    }

    summary = {
        "n_scenarios_per_group": structure["n_scenarios_per_group"],
        "n_unique_claims_per_group": structure["n_unique_claims_per_group"],
        "mean_reuse_rate": structure["mean_reuse_rate"],
        "exact_overlap_count": isolation["exact_overlap_count"],
        "shared_fragment_count_ge8": isolation["shared_fragment_count_ge8"],
        "wording_holdout_feasible": isolation["wording_holdout_feasible"],
        "sides": {k: {kk: vv for kk, vv in v.items() if kk != "rows"}
                  for k, v in sides.items()},
        "group_paired": {k: v for k, v in paired.items() if k != "per_group"},
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.write:
        REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
        REPORT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        REPORT_MD.write_text(render_markdown(payload), encoding="utf-8")
        print(f"[out] {REPORT_JSON.relative_to(REPO)}")
        print(f"[out] {REPORT_MD.relative_to(REPO)}")

    # 返回 0：审计完成即成功。「留出不可行」是结论，不是失败。
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

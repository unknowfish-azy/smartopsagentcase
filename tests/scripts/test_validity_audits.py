"""EXP-CIRC-001 / EXP-WORDING-001 效度审计单测。

这两条审计不是「性能更好」的证据，而是**边界证据**：它们决定既有基线指标
能被引用到什么程度。因此测试的重点是：

1. 审计逻辑本身正确（列联、平凡规则、Fisher 精确检验）；
2. **循环确实成立**被如实检出（回归保护：若哪天数据集修好了，这些断言会失败，
   提醒同步更新 fact-sheet 口径——这是刻意的）；
3. 措辞留出不可行被如实检出（重叠数 > 0）。
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

SAMPLES = REPO / "SmartOps-Dataset" / "Controlled" / "v1" / "samples.jsonl"
CIRC_SCRIPT = REPO / "scripts" / "audit_label_probe_circularity.py"
WORD_SCRIPT = REPO / "scripts" / "build_wording_holdout.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def circ():
    return _load(CIRC_SCRIPT, "audit_label_probe_circularity")


@pytest.fixture(scope="module")
def word():
    return _load(WORD_SCRIPT, "build_wording_holdout")


@pytest.fixture(scope="module")
def controlled():
    rows = [json.loads(line) for line in SAMPLES.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    return [r for r in rows if r["dataset_type"] == "verification"]


# ---------------------------------------------------------------- 循环审计
def test_circularity_is_detected_on_controlled_set(circ, controlled):
    """核心回归保护：主指标子集上标签由探针健康度唯一决定。"""
    result = circ.audit_rows(controlled, "controlled_all")
    assert result["single_bit_separable_binary_subset"] is True
    assert result["binary_trivial_rate"] == 1.0
    # 反极性必须全错，排除方向巧合
    assert result["binary_reversed_correct"] == 0


def test_circularity_full_label_table_is_diagonal(circ, controlled):
    """不健康 ⇒ 非 SUCCESS；健康 ⇒ SUCCESS。"""
    result = circ.audit_rows(controlled, "controlled_all")
    table = result["label_x_probe_health"]
    assert table.get("SUCCESS|True", 0) == 36
    assert table.get("SUCCESS|False", 0) == 0
    assert table.get("FALSE_SUCCESS|True", 0) == 0
    # FAILED/UNKNOWN 全部落在不健康侧
    assert table.get("FAILED|True", 0) == 0
    assert table.get("UNKNOWN|True", 0) == 0


def test_fisher_exact_p_value_is_tiny(circ, controlled):
    """关联强度：完美对角列联的 Fisher 单侧 p 应极小。"""
    result = circ.audit_rows(controlled, "controlled_all")
    assert result["fisher_one_sided_p"] is not None
    assert result["fisher_one_sided_p"] < 1e-9


def test_fisher_implementation_matches_known_case(circ):
    """自检：2x2 完美对角应给出极小 p；无关联时不应极小。"""
    tiny = circ.fisher_exact_one_sided(36, 0, 0, 108)
    assert tiny < 1e-9
    # 均衡列联（无关联）的 p 不会极小
    neutral = circ.fisher_exact_one_sided(50, 50, 50, 50)
    assert neutral > 0.05
    # 零分母退化为 1.0，不得抛异常
    assert circ.fisher_exact_one_sided(0, 0, 0, 0) == 1.0


def test_circularity_coverage_gap_is_reported(circ, controlled):
    """主指标只覆盖一半样本，其余被分母排除——缺口必须显式可见。"""
    result = circ.audit_rows(controlled, "controlled_all")
    assert result["coverage_rate"] == 0.5
    assert result["denies_success_n"] == 68
    assert result["out_of_taxonomy_n"] == 4


def test_audit_does_not_modify_inputs(circ, controlled):
    """审计只读：不得改动样本对象。"""
    before = json.dumps(controlled[:5], ensure_ascii=False, sort_keys=True)
    circ.audit_rows(controlled, "controlled_all")
    after = json.dumps(controlled[:5], ensure_ascii=False, sort_keys=True)
    assert before == after


# ---------------------------------------------------------------- 措辞审计
def test_wording_holdout_is_infeasible(word, controlled):
    """每组仅 2 场景 × 3 模板，切开后必然有 claim 重叠。"""
    per_group: dict[str, list[dict]] = {}
    for s in controlled:
        per_group.setdefault(s["metadata"]["root_cause_group"], []).append(s)
    held, dev = [], []
    for key in sorted(per_group):
        rows = sorted(per_group[key], key=lambda r: r["sample_id"])
        held.extend(rows[:word.HELD_VARIANTS_PER_GROUP])
        dev.extend(rows[word.HELD_VARIANTS_PER_GROUP:])

    iso = word.isolation_check(held, dev)
    assert iso["exact_overlap_count"] > 0
    assert iso["wording_holdout_feasible"] is False
    assert iso["shared_fragment_count_ge8"] > 0


def test_group_structure_is_two_scenarios_per_group(word, controlled):
    """结构事实：24 组，每组 2 个场景，唯一 claim 串 3–6 条。"""
    st = word.group_structure(controlled)
    assert st["n_groups"] == 24
    assert set(st["n_scenarios_per_group"]) == {2}
    assert min(st["n_unique_claims_per_group"]) >= 3
    assert max(st["n_unique_claims_per_group"]) <= 6
    assert st["mean_reuse_rate"] > 0


def test_same_group_label_is_unique(word, controlled):
    """组内标签唯一——这是『有效样本量按组数计』的前提。"""
    by_group: dict[str, set[str]] = {}
    for r in controlled:
        by_group.setdefault(r["metadata"]["root_cause_group"], set()).add(
            r["ground_truth"]["label"])
    assert all(len(v) == 1 for v in by_group.values())


def test_group_paired_consistency_unit_is_group(word, controlled):
    """配对单位必须是组，且一致率可算。"""
    per_group: dict[str, list[dict]] = {}
    for s in controlled:
        per_group.setdefault(s["metadata"]["root_cause_group"], []).append(s)
    held, dev = [], []
    for key in sorted(per_group):
        rows = sorted(per_group[key], key=lambda r: r["sample_id"])
        held.extend(rows[:word.HELD_VARIANTS_PER_GROUP])
        dev.extend(rows[word.HELD_VARIANTS_PER_GROUP:])

    sides = {"dev": word.side_metrics("d", dev), "held": word.side_metrics("h", held)}
    group_of = {r["sample_id"]: r["metadata"]["root_cause_group"] for r in held + dev}
    group_label = {r["metadata"]["root_cause_group"]: r["ground_truth"]["label"]
                   for r in held + dev}
    paired = word.group_paired_consistency(sides["dev"], sides["held"], group_of, group_label)
    assert paired["unit"] == "root_cause_group"
    assert paired["n_groups"] == 24
    assert 0.0 <= paired["agreement_rate"] <= 1.0


def test_normalize_matches_classify_claim_contract(word):
    """归一化口径须与 classify_claim 一致（小写 + 折叠空白）。"""
    assert word.normalize("  Redis   正常 ") == "redis 正常"
    assert word.normalize("") == ""

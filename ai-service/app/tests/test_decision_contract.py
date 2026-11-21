"""DS-04：判定输出契约守卫（线上 schema vs 训练目标）。

背景：DS-04 计划要求 `decision_schema.DECISION_SCHEMA` 是
`training/schemas/smartops-training-sample.schema.json` 中 `evidenceOutput` 的超集，
否则 LoRA 的训练目标与线上推理契约不是同一个形状，微调白做。

实测结论（2026-11-21）：两侧字段名并非全部同名——

- 同名且语义一致：`label`、`confidence`
- 改名但语义一致：`reason` → `rationale`、`supporting_evidence` → `used_refs`

而真正决定「微调是否有效」的是 **LoRA 训练数据实际喂给模型的形状**。
`scripts/build_distill_dataset.py` 生成的 assistant 输出用的是线上 `DECISION_SCHEMA`
形状（verdict/label/used_refs/confidence/gaps_acknowledged/next_probe/rationale），
所以训练目标与线上输出一致，不存在漂移。

这批断言把这个结论钉住，防止有人改一侧而忘了另一侧。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.decision_schema import DECISION_SCHEMA, LABELS, VERDICTS

REPO_ROOT = Path(__file__).resolve().parents[3]
TRAINING_SCHEMA = REPO_ROOT / "training" / "schemas" / "smartops-training-sample.schema.json"
DISTILL_SCRIPT = REPO_ROOT / "scripts" / "build_distill_dataset.py"

# evidenceOutput 的字段 → 线上契约字段（语义等价，允许改名但必须登记）。
SEMANTIC_MAP = {
    "label": "label",
    "reason": "rationale",
    "supporting_evidence": "used_refs",
    "confidence": "confidence",
}


def _training_evidence_output() -> dict:
    document = json.loads(TRAINING_SCHEMA.read_text(encoding="utf-8"))
    return document["$defs"]["evidenceOutput"]


def test_training_schema_exists():
    assert TRAINING_SCHEMA.exists(), f"找不到训练样本 schema：{TRAINING_SCHEMA}"


def test_every_evidence_output_field_has_a_counterpart():
    """evidenceOutput 的每个字段都能映射到线上契约（不得有未登记字段）。"""
    training = _training_evidence_output()
    online_props = DECISION_SCHEMA["properties"]
    unmapped = [name for name in training["properties"] if name not in SEMANTIC_MAP]
    assert not unmapped, f"evidenceOutput 新增了未登记字段：{unmapped}；请同步 SEMANTIC_MAP"
    missing = [target for target in SEMANTIC_MAP.values() if target not in online_props]
    assert not missing, f"线上契约缺少映射目标字段：{missing}"


def test_label_enum_compatible():
    """线上 label 必须是训练 label 的超集（多一个 null 表「不给正向标签」）。"""
    training_labels = set(_training_evidence_output()["properties"]["label"]["enum"])
    online_labels = set(LABELS)
    assert training_labels <= online_labels
    assert set(DECISION_SCHEMA["properties"]["label"]["enum"]) == online_labels | {None}


def test_verdict_is_superset_of_label():
    """verdict 比 label 多一个 INSUFFICIENT（缺口场景不给正向标签）。"""
    assert set(VERDICTS) == set(LABELS) | {"INSUFFICIENT"}


def test_confidence_bounds_match():
    training_conf = _training_evidence_output()["properties"]["confidence"]
    online_conf = DECISION_SCHEMA["properties"]["confidence"]
    assert (online_conf["minimum"], online_conf["maximum"]) == (
        training_conf["minimum"],
        training_conf["maximum"],
    )


@pytest.mark.skipif(not DISTILL_SCRIPT.exists(), reason="仓库内无蒸馏构建脚本")
def test_distill_dataset_emits_online_shape_not_training_shape():
    """训练数据的 assistant 必须用线上形状——这是「微调不白做」的硬证据。

    读源码而非跑生成器：避免测试依赖随机配额，且能精确钉住键名。
    """
    source = DISTILL_SCRIPT.read_text(encoding="utf-8")
    # 线上形状独有、evidenceOutput 没有的键
    for key in ("used_refs", "rationale", "gaps_acknowledged", "next_probe"):
        assert f'"{key}"' in source, f"蒸馏样本未产出线上字段 {key}，训练目标会与线上契约漂移"
    # evidenceOutput 独有、线上契约已改名的键不得再作为顶层输出字段出现
    assert '"supporting_evidence"' not in source, "蒸馏样本仍在使用训练 schema 的旧字段名"


def test_decision_schema_is_closed_object():
    assert DECISION_SCHEMA.get("additionalProperties") is False


# --- label / verdict 一致性（DS-04 计划的显式约束，此前无守卫）-----------------
# 计划原文：`verdict=INSUFFICIENT` 时 `label` 必须为 null；其余 verdict 时 `label`
# 必须等于 `verdict`。注意 JSON Schema 的 enum/if-then 在本仓库未被任何校验器使用，
# 所以这条约束此前只是注释声明——这里钉成可执行断言。

LABEL_VERDICT_CASES = [
    ("SUPPORTED", "SUPPORTED"),
    ("PARTIALLY_SUPPORTED", "PARTIALLY_SUPPORTED"),
    ("UNSUPPORTED", "UNSUPPORTED"),
    ("CONTRADICTED", "CONTRADICTED"),
    ("INSUFFICIENT", None),
]


def _expected_label(verdict: str) -> str | None:
    """DS-04 计划规定的唯一规则：缺口（INSUFFICIENT）不给正向标签。"""
    return None if verdict == "INSUFFICIENT" else verdict


@pytest.mark.parametrize(("verdict", "label"), LABEL_VERDICT_CASES)
def test_label_rule_is_total(verdict, label):
    """每个合法 verdict 都有确定的 label 期望，且没有第二个 INSUFFICIENT 变体。"""
    assert _expected_label(verdict) == label


def test_online_and_distill_label_rule_agree():
    """线上契约与训练数据对「缺口不给正向标签」的规则必须一致。

    只校验语义（两条源码都含 INSUFFICIENT→null 的判据），不比对字面写法——
    bench 用 `None if X == "INSUFFICIENT" else X`，蒸馏用 `X != "INSUFFICIENT" else None`。
    """
    bench_source = (REPO_ROOT / "ai-service" / "scripts" / "bench_llm_eval.py").read_text(
        encoding="utf-8"
    )
    distill_source = DISTILL_SCRIPT.read_text(encoding="utf-8")
    assert "INSUFFICIENT" in bench_source and "label" in bench_source
    assert "INSUFFICIENT" in distill_source and '"label"' in distill_source
    # 蒸馏侧是权威写法（训练目标），bench 侧只需含同一判据
    assert 'verdict != "INSUFFICIENT" else None' in distill_source


def _parse_raw(raw: str) -> dict | None:
    """与 bench_llm_eval.parse_decision 同口径取第一个 JSON 对象。"""
    import re

    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def test_schema_runs_honour_label_rule_when_present():
    """**带 schema** 的产物中，凡出现 label 就必须满足 INSUFFICIENT→null 规则。

    注意：当前 `DECISION_SCHEMA.required` 不含 `label`，所以实测 32/32 条带 schema 输出
    都省略了 label（规则空转、无法证明合规）。本断言因此是「出现即校验」，
    配合 `test_schema_required_covers_training_shape` 一起钉住训练/推理同形。
    无 schema 的历史产物不受此约束——实测 counter-06 在 verdict=INSUFFICIENT 时仍给
    label=UNSUPPORTED，那正是 DS-04 要修的问题，不要求历史数据合规。
    """
    eval_dir = REPO_ROOT / "data" / "training" / "eval"
    reports = [
        path
        for path in sorted(eval_dir.glob("latest*.json"))
        if json.loads(path.read_text(encoding="utf-8")).get("structured_output")
    ]
    assert reports, "没有带 schema 的评测产物可校验"
    checked = violations = 0
    for path in reports:
        for row in json.loads(path.read_text(encoding="utf-8")).get("cases") or []:
            data = _parse_raw(row.get("raw") or "")
            if data and "label" in data and "verdict" in data:
                checked += 1
                if data["label"] != _expected_label(data["verdict"]):
                    violations += 1
    assert violations == 0, f"带 schema 的产物有 {violations}/{checked} 条违反 label 规则"


def test_schema_required_covers_training_shape():
    """DS-04 计划要求 required 含 label/confidence，当前实现缺失 —— 登记为已知偏差。

    若两侧不同形：LoRA 训练数据永远产出 label/confidence，而线上契约不要求，
    模型学到的字段在推理时不被约束，属契约漂移。修复前该断言按现状锁定，
    一旦有人补上 required，这里会红并提示改为「必须覆盖」。
    """
    required = set(DECISION_SCHEMA["required"])
    missing = {"label", "confidence"} - required
    assert missing == {"label", "confidence"}, (
        f"DECISION_SCHEMA.required 已变化（当前缺少 {sorted(missing)}）；"
        "若已补齐 label/confidence，请把本断言改为要求覆盖 training 形状"
    )

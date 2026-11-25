"""P2-7 / C 骨架单元测试（反事实生成逻辑**未实现**，此处只钉契约与口径）。

对应门禁：
- C-G1 构造可复现：Plan 参数必须完整落盘、非法计划必须拒绝执行；
- C-G2 循环披露：报告/数据卡必须携带「生成器给定因果结构」的披露；
- C-G3 对照：`a1_gain` 只有在 Holm 校正后显著且区间不含 0 才可判「有增益」；
- C-G4 有效样本量：必须给 ICC/DEFF 有效 n，禁止用名义 n 撑区间。

另钉住骨架期已修的三处「会让诚实机制静默失效」的缺陷：
`holm_bonferroni` 返回 dict 而非 list、bootstrap 键名是 `ci_low/ci_high`、
ICC 无 `m` 键（有效 n 不得恒等于名义 n）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
AI_SERVICE = REPO / "ai-service"
for _path in (str(AI_SERVICE), str(REPO)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from app.causal import metrics as cm  # noqa: E402
from app.causal.schema import (  # noqa: E402
    CounterfactualPair,
    FlipRecord,
    MetricResult,
    PairVerdict,
    Plan,
    PlanError,
)
from app.causal.training import (  # noqa: E402
    DEFAULT_REG_WEIGHT,
    REG_WEIGHTS,
    CausalTrainConfig,
    CausalTrainingNotImplemented,
    causal_regularization_loss,
    counterfactual_augmentation_pairs,
)


def _plan(**overrides) -> Plan:
    raw = {
        "scenario": "synthetic-topology-v1",
        "model": "graphsage",
        "seed": 20261125,
        "n_events": 200,
        "n_pairs": 100,
        "note": "",
    }
    raw.update(overrides)
    return Plan(**raw)


# ---------------------------------------------------------------------------
# 数据契约
# ---------------------------------------------------------------------------


def test_plan_validates_seed_and_sizes():
    with pytest.raises(PlanError):
        _plan(seed=-1).validate()
    with pytest.raises(PlanError):
        _plan(n_events=0).validate()
    with pytest.raises(PlanError):
        _plan(n_boot=50).validate()          # 区间样本太少不可解释


def test_plan_rejects_unknown_fields_and_bad_policy():
    with pytest.raises(PlanError):
        Plan.from_dict({"scenario": "s", "model": "m", "seed": 1, "n_events": 2,
                        "意外字段": 1})
    with pytest.raises(PlanError):
        _plan().to_dict() and Plan(
            scenario="s", model="m", seed=1, n_events=2, do_node_policy="random",
        ).validate()


def test_plan_roundtrip_keeps_all_generator_params():
    plan = _plan(note="骨架")
    assert Plan.from_dict(plan.to_dict()).to_dict() == plan.to_dict()


def test_counterfactual_pair_requires_distinct_roots():
    with pytest.raises(PlanError):
        CounterfactualPair(
            pair_id="p1", topology_id="t1", root_v="a", root_w="a",
            sample_v_ref="s1", sample_w_ref="s2",
        ).validate()


def test_flip_record_none_is_not_judgeable():
    """前后任一缺失 → flipped=None，且**不得**计入任何分母。"""

    record = FlipRecord(
        case_id="c1", model="m", intervened_node="v",
        is_true_root=True, top1_before="a", top1_after=None,
    )
    assert record.flipped is None
    result = cm.flip_rate([record])
    assert result.status == "NOT_RUN" and result.n == 0 and result.value is None


# ---------------------------------------------------------------------------
# 指标纯函数与 C-G3
# ---------------------------------------------------------------------------


def test_flip_rates_report_together_and_use_wilson():
    flips = [
        FlipRecord(f"c{i}", "m", "v", True, "a", "b").to_dict() for i in range(8)
    ] + [
        FlipRecord(f"n{i}", "m", "w", False, "a", "a").to_dict() for i in range(8)
    ]
    records = [FlipRecord(**row) for row in flips]

    main = cm.flip_rate(records)
    collateral = cm.collateral_flip_rate(records)

    assert main.status == "COMPLETED" and main.value == 1.0 and main.n == 8
    assert collateral.status == "COMPLETED" and collateral.value == 0.0
    assert main.wilson_95 is not None and collateral.wilson_95 is not None
    # 单看 flip_rate 会被「总是改判」刷满 → note 必须提示同时引用误伤率
    assert "collateral" in main.note


def test_empty_inputs_are_not_run_not_zero():
    for result in (cm.flip_rate([]), cm.collateral_flip_rate([]), cm.pair_accuracy([])):
        assert isinstance(result, MetricResult)
        assert result.status == "NOT_RUN"
        assert result.value is None and result.n == 0


def test_compare_models_identical_records_is_not_run():
    """b=c=0 时**必须** NOT_RUN，不得记 p=1 或 0。"""

    outcome = cm.compare_models([True] * 10, [True] * 10, n_boot=200, seed=1)
    assert outcome["status"] == "NOT_RUN"
    assert outcome["significant_after_holm"] is False
    assert outcome["ci_low"] is not None      # 回归：不得再读不存在的 low/high 键


def test_compare_models_detects_significant_gain():
    """仅因果模型命中的样本足够多 → Holm 显著且区间不含 0。"""

    causal = [True] * 30
    corr = [False] * 20 + [True] * 10
    outcome = cm.compare_models(causal, corr, alpha=0.05, n_boot=500, seed=7)
    assert outcome["status"] == "COMPLETED"
    assert outcome["b_only_causal"] == 20 and outcome["c_only_corr"] == 0
    assert outcome["value"] == pytest.approx(20 / 30)
    assert outcome["significant_after_holm"] is True
    assert outcome["holm_adjusted_p"] < 0.05
    assert outcome["ci_low"] > 0.0


def test_compare_models_lenient_case_is_not_significant():
    """差距小且双向不一致 → 必须写「未证明增益」。"""

    causal = [True] * 12 + [False] * 8
    corr = [True] * 10 + [False] * 10
    outcome = cm.compare_models(causal, corr, n_boot=300, seed=3)
    assert outcome["status"] == "COMPLETED"
    assert outcome["significant_after_holm"] is False


# ---------------------------------------------------------------------------
# C-G4 有效样本量
# ---------------------------------------------------------------------------


def test_effective_n_shrinks_when_groups_are_homogeneous():
    """组内完全同质 → ICC=1 → DEFF=m → 有效 n = 名义 n / m。

    这条测试专门钉住旧骨架的缺陷：旧实现读不存在的 ``icc["m"]``，
    使 DEFF 恒为 1、有效 n 恒等于名义 n，C-G4 形同虚设。
    """

    groups = [[1.0] * 4, [0.0] * 4] * 4    # 8 组、每组 4 个；组内全同、组间不同
    outcome = cm.effective_n(groups)
    assert outcome["icc"] == 1.0
    assert outcome["deff"] == pytest.approx(4.0)
    assert outcome["effective_n"] == pytest.approx(8.0)   # 32 / 4
    assert outcome["avg_group_size"] == 4.0


def test_effective_n_not_run_when_too_few_groups():
    outcome = cm.effective_n([[1.0, 0.0]])
    assert outcome["icc_status"] == "NOT_RUN"
    assert outcome["effective_n"] is None and outcome["deff"] is None
    assert "禁止用名义 n" in outcome["note"]


# ---------------------------------------------------------------------------
# C3 训练变体骨架
# ---------------------------------------------------------------------------


def test_train_config_defaults_to_no_regularizer():
    config = CausalTrainConfig(base_model="graphsage", variant="causal_regularizer")
    config.validate()
    assert config.reg_weight == 0.0 == DEFAULT_REG_WEIGHT
    assert REG_WEIGHTS == (0.0, 0.5, 1.0)
    assert config.is_default_behaviour is True       # C-G5：默认不变


def test_train_config_rejects_off_grid_weight_and_low_seed_count():
    with pytest.raises(ValueError):
        CausalTrainConfig(base_model="g", variant="causal_regularizer",
                          reg_weight=0.7).validate()
    with pytest.raises(ValueError):
        CausalTrainConfig(base_model="g", variant="causal_regularizer",
                          n_seeds=2).validate()


def test_training_entries_raise_not_implemented():
    config = CausalTrainConfig(base_model="g", variant="causal_regularizer")
    with pytest.raises(CausalTrainingNotImplemented):
        causal_regularization_loss(config, [0.1], [0.2])
    with pytest.raises(CausalTrainingNotImplemented):
        counterfactual_augmentation_pairs(_plan())


# ---------------------------------------------------------------------------
# 脚本入口（骨架行为）
# ---------------------------------------------------------------------------


def _load_script(name: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        name, AI_SERVICE / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_script_writes_card_without_samples(tmp_path, capsys):
    build_cf = _load_script("build_counterfactual")

    card_path = tmp_path / "card.json"
    rc = build_cf.main([
        "--scenario", "synthetic-topology-v1", "--model", "graphsage",
        "--seed", "20261125", "--n-events", "200", "--n-pairs", "100",
        "--out", str(card_path),
    ])
    assert rc == 0
    card = json.loads(card_path.read_text(encoding="utf-8"))
    assert card["implementation_status"] == "NOT_IMPLEMENTED"
    assert card["plan"]["seed"] == 20261125          # C-G1：参数完整落盘
    assert card["artifacts"] == []                   # 骨架期不得产出任何样本
    assert "生成器给定" in card["loop_disclosure"]   # C-G2 披露
    assert "未实现" in capsys.readouterr().out


def test_build_script_rejects_invalid_plan(tmp_path):
    build_cf = _load_script("build_counterfactual")

    rc = build_cf.main([
        "--scenario", "s", "--model", "m", "--seed", "-1",
        "--n-events", "10", "--out", str(tmp_path / "card.json"),
    ])
    assert rc == 2
    assert not (tmp_path / "card.json").exists()     # 非法计划不落盘


def test_eval_script_missing_file_is_an_error(tmp_path):
    eval_cf = _load_script("eval_counterfactual")

    rc = eval_cf.main(["--flips", str(tmp_path / "nope.jsonl"),
                       "--report", str(tmp_path / "r.json")])
    assert rc == 2          # 指定路径却不存在 → 报错，不得静默 NOT_RUN


def test_eval_script_without_inputs_is_not_run(tmp_path):
    eval_cf = _load_script("eval_counterfactual")

    report = tmp_path / "cf.json"
    rc = eval_cf.main(["--report", str(report)])
    assert rc == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "NOT_RUN"
    assert payload["metrics"]["counterfactual_flip_rate"]["status"] == "NOT_RUN"
    assert payload["metrics"]["a1_gain"]["status"] == "NOT_RUN"
    assert payload["effective_n"]["effective_n"] is None
    assert "生成器给定" in payload["loop_disclosure"]
    assert report.with_suffix(".md").exists()

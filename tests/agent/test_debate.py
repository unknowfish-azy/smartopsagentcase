"""多 Agent 辩论（P2-7 / A1 + A2）单元测试。

对应门禁：
- A-G1：纯函数单测——收敛 / 变更 / 升级三判据正确，反驳后 top1 变化被识别；
- A-G2：防循环回归——「全角色同一证据池」的负对照必须判为无效实验。
"""

from __future__ import annotations

import pytest

from agent.subagents.debate import (
    Conclusion,
    DebateRunner,
    Rebuttal,
    detect_changes,
    judge_verdict,
)
from agent.subagents.debate_rules import RuleRoleAgent
from agent.subagents.evidence_channels import (
    CHANNEL_PROBE_TYPES,
    CHANNEL_ROLES,
    ChannelView,
    EvidenceItem,
    partition_items,
    shared_pool_views,
    validate_isolation,
)


def _conclusion(role: str, top1: str | None, **kwargs) -> Conclusion:
    return Conclusion(role=role, top1=top1, **kwargs)


def _views(**items: list[EvidenceItem]) -> dict[str, ChannelView]:
    return {
        role: ChannelView(role=role, items=tuple(items.get(role, ())))
        for role in CHANNEL_ROLES
    }


# ---------------------------------------------------------------------------
# A-G1：三判据
# ---------------------------------------------------------------------------


def test_detect_changes_flags_top1_transitions():
    initial = {
        "a": _conclusion("a", "x"),
        "b": _conclusion("b", "y"),
        "c": _conclusion("c", None),
    }
    final = {
        "a": _conclusion("a", "x"),      # 未变
        "b": _conclusion("b", "z"),      # 变了
        "c": _conclusion("c", "y"),      # 弃权 → 有结论
    }
    assert detect_changes(initial, final) == ("b", "c")


def test_detect_changes_is_empty_when_nothing_moved():
    initial = {"a": _conclusion("a", "x"), "b": _conclusion("b", None)}
    assert detect_changes(initial, dict(initial)) == ()


def test_verdict_converged_when_all_active_agree():
    initial = {
        "a": _conclusion("a", "x"),
        "b": _conclusion("b", "x"),
        "c": _conclusion("c", None),
    }
    verdict = judge_verdict(initial, dict(initial), rounds=1, max_rounds=2)

    assert verdict.status == "converged"
    assert verdict.converged is True
    assert verdict.changed is False
    assert verdict.final_top1 == "x"
    assert verdict.agree_roles == ("a", "b")
    assert verdict.abstain_roles == ("c",)


def test_verdict_escalated_on_persistent_disagreement():
    initial = {"a": _conclusion("a", "x"), "b": _conclusion("b", "y")}
    verdict = judge_verdict(initial, dict(initial), rounds=2, max_rounds=2)

    assert verdict.status == "escalated"
    assert verdict.converged is False
    assert verdict.final_top1 is None
    assert verdict.agree_roles == ()


def test_verdict_escalated_when_every_role_abstains():
    initial = {"a": _conclusion("a", None), "b": _conclusion("b", None)}
    verdict = judge_verdict(initial, dict(initial), rounds=1, max_rounds=2)

    assert verdict.status == "escalated"
    assert verdict.final_top1 is None
    assert verdict.abstain_roles == ("a", "b")
    assert "弃权" in verdict.reason


def test_verdict_changed_true_when_rebuttal_revises_top1():
    initial = {"a": _conclusion("a", "x"), "b": _conclusion("b", "x")}
    final = {"a": _conclusion("a", "x"), "b": _conclusion("b", "y")}
    verdict = judge_verdict(initial, final, rounds=1, max_rounds=2)

    assert verdict.changed is True
    assert verdict.changed_roles == ("b",)
    assert verdict.status == "escalated"


# ---------------------------------------------------------------------------
# 运行器：反驳必须真的改变结论
# ---------------------------------------------------------------------------


class _StubAgent:
    """两个角色：log_diagnosis 先给 x，metric_inspector 先给 y；反驳轮后者采纳前者。"""

    def __init__(self) -> None:
        self.rebut_calls: list[str] = []

    def conclude(self, role, question, view):
        top1 = {
            "log_diagnosis": "x",
            "metric_inspector": "y",
            "topology_inspector": None,
            "change_auditor": None,
        }[role]
        return _conclusion(role, top1, evidence=(f"E-{role}",))

    def rebut(self, role, question, view, others, previous):
        self.rebut_calls.append(role)
        if role == "metric_inspector":
            return Rebuttal(
                role=role, agree_with="log_diagnosis", dispute=None,
                new_evidence=("E-log_diagnosis",), revised_top1="x", rationale="被说服",
            )
        return Rebuttal(
            role=role, agree_with=None, dispute="维持",
            new_evidence=(), revised_top1=previous.top1, rationale="维持",
        )


def test_runner_reaches_convergence_and_records_change():
    runner = DebateRunner(_StubAgent(), max_rebuttal_rounds=2)
    record = runner.run("q", _views())

    assert record.verdict.status == "converged"
    assert record.verdict.final_top1 == "x"
    assert record.verdict.changed is True
    assert record.verdict.changed_roles == ("metric_inspector",)
    assert record.verdict.rounds == 1
    assert len(record.rounds) == 2          # round 0 + 一轮反驳
    assert len(record.rebuttals) == 1
    assert record.to_dict()["verdict"]["final_top1"] == "x"


class _DeadlockAgent:
    def conclude(self, role, question, view):
        return _conclusion(
            role,
            "x" if role == "log_diagnosis" else "y",
            evidence=(f"E-{role}",),
        )

    def rebut(self, role, question, view, others, previous):
        return Rebuttal(
            role=role, agree_with=None, dispute="证据不同",
            new_evidence=(), revised_top1=previous.top1, rationale="维持",
        )


def test_runner_escalates_after_hitting_round_cap():
    runner = DebateRunner(_DeadlockAgent(), max_rebuttal_rounds=2)
    record = runner.run("q", _views())

    assert record.verdict.status == "escalated"
    assert record.verdict.converged is False
    assert record.verdict.final_top1 is None
    assert record.verdict.rounds == 2
    assert len(record.rebuttals) == 2


def test_runner_rejects_missing_channel_view():
    runner = DebateRunner(_StubAgent())
    with pytest.raises(ValueError, match="缺少通道视图"):
        runner.run("q", {})


# ---------------------------------------------------------------------------
# A2：证据通道隔离
# ---------------------------------------------------------------------------


def _items():
    return [
        EvidenceItem("E1", "log_line"),
        EvidenceItem("E2", "memory"),
        EvidenceItem("E3", "icmp"),
        EvidenceItem("E4", "config_value"),
    ]


def test_partition_is_disjoint_and_complete():
    views = partition_items(_items())
    ids = [set(view.ids) for view in views.values()]

    assert sorted(sum((list(s) for s in ids), [])) == ["E1", "E2", "E3", "E4"]
    for i, left in enumerate(ids):
        for right in ids[i + 1:]:
            assert left & right == set()
    assert set(views) == set(CHANNEL_ROLES)


def test_partition_rejects_unknown_probe_type():
    with pytest.raises(ValueError, match="不在封闭词表内"):
        partition_items([EvidenceItem("E9", "telepathy")])


def test_partition_rejects_disabled_role_evidence():
    with pytest.raises(ValueError, match="未启用的通道"):
        partition_items(_items(), role_names=("log_diagnosis",))


def test_validate_isolation_accepts_partition():
    report = validate_isolation(partition_items(_items()))

    assert report.valid is True
    assert report.reasons == ()
    assert report.shared_id_pairs == ()


def test_validate_isolation_flags_role_reading_outside_vocabulary():
    views = partition_items(_items())
    broken = dict(views)
    broken["log_diagnosis"] = ChannelView(
        role="log_diagnosis",
        items=views["log_diagnosis"].items + views["metric_inspector"].items,
    )
    report = validate_isolation(broken)

    assert report.valid is False
    assert "log_diagnosis" in report.offending_roles
    assert report.shared_id_pairs  # 与 metric_inspector 共享


# ---------------------------------------------------------------------------
# A-G2：防同源负对照
# ---------------------------------------------------------------------------


def test_shared_pool_negative_control_is_invalid():
    """所有角色看同一份证据池 → 必须判为无效实验，而不是高分。"""

    report = validate_isolation(shared_pool_views(_items()))

    assert report.valid is False
    assert len(report.shared_id_pairs) == 6   # C(4,2)
    assert report.reasons


def test_channel_vocabularies_are_disjoint():
    seen: dict[str, str] = {}
    for role, probe_types in CHANNEL_PROBE_TYPES.items():
        for probe_type in probe_types:
            assert probe_type not in seen, f"{probe_type} 出现在两个通道"
            seen[probe_type] = role


# ---------------------------------------------------------------------------
# 确定性规则角色
# ---------------------------------------------------------------------------


def test_rule_agent_abstains_on_empty_view():
    agent = RuleRoleAgent()
    conclusion = agent.conclude(
        "log_diagnosis", "q", ChannelView(role="log_diagnosis", items=())
    )

    assert conclusion.top1 is None
    assert conclusion.confidence is None
    assert conclusion.evidence == ()


def test_rule_agent_cites_evidence_and_ranks_by_support():
    agent = RuleRoleAgent()
    view = ChannelView(role="metric_inspector", items=(
        EvidenceItem("E1", "memory"),
        EvidenceItem("E2", "oom_kills"),
    ))
    conclusion = agent.conclude("metric_inspector", "q", view)

    assert conclusion.top1 == "l4-oom"
    assert set(conclusion.evidence) == {"E1", "E2"}
    assert conclusion.support == 2
    assert conclusion.confidence == 1.0


def test_rule_agent_rebuttal_adopts_stronger_candidate_in_its_set():
    agent = RuleRoleAgent()
    # metric_threshold 指向 4 个候选；最具体的是 db-redis（只被 2 类探针指向）
    view = ChannelView(role="metric_inspector", items=(
        EvidenceItem("E1", "metric_threshold"),
    ))
    previous = agent.conclude("metric_inspector", "q", view)
    assert previous.top1 == "db-redis"

    other = _conclusion(
        "topology_inspector", "http-latency",
        candidates=("http-latency",), evidence=("E9",), support=3,
    )

    rebuttal = agent.rebut(
        "metric_inspector", "q", view, {"topology_inspector": other}, previous
    )

    assert rebuttal.revised_top1 == "http-latency"
    assert rebuttal.agree_with == "topology_inspector"
    assert rebuttal.new_evidence == ("E9",)


def test_rule_agent_holds_when_challenger_is_outside_candidate_set():
    agent = RuleRoleAgent()
    view = ChannelView(role="metric_inspector", items=(
        EvidenceItem("E1", "memory"),
    ))
    previous = agent.conclude("metric_inspector", "q", view)
    other = _conclusion(
        "topology_inspector", "net-dns",
        candidates=("net-dns",), evidence=("E9",), support=5,
    )

    rebuttal = agent.rebut(
        "metric_inspector", "q", view, {"topology_inspector": other}, previous
    )

    assert rebuttal.revised_top1 == "l4-oom"
    assert rebuttal.agree_with is None
    assert rebuttal.dispute and "E1" in rebuttal.dispute


def test_rule_agent_holds_when_challenger_has_weaker_evidence():
    agent = RuleRoleAgent()
    view = ChannelView(role="metric_inspector", items=(
        EvidenceItem("E1", "cache_ping"),
        EvidenceItem("E2", "metric_threshold"),
    ))
    previous = agent.conclude("metric_inspector", "q", view)
    other = _conclusion(
        "topology_inspector", "http-latency",
        candidates=("http-latency",), evidence=("E9",), support=0,
    )

    rebuttal = agent.rebut(
        "metric_inspector", "q", view, {"topology_inspector": other}, previous
    )

    assert rebuttal.agree_with is None
    assert rebuttal.revised_top1 == previous.top1


def test_rule_agent_keeps_abstaining_role_abstained():
    agent = RuleRoleAgent()
    view = ChannelView(role="change_auditor", items=())
    previous = agent.conclude("change_auditor", "q", view)
    other = _conclusion("log_diagnosis", "l4-oom", evidence=("E1",), support=2)

    rebuttal = agent.rebut(
        "change_auditor", "q", view, {"log_diagnosis": other}, previous
    )

    assert rebuttal.revised_top1 is None
    assert "弃权" in rebuttal.rationale

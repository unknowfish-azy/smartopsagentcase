"""W2 验收：SecurityBrief 六感简报的契约、行为准则与确定性。

覆盖：
1. 契约字段 100% 齐全（smartops.security_brief.v1）；
2. 高危操作必答"影响面 / 回滚 / 验证 / 审批"（S2）；
3. confidence < 0.6 必 requires_human（S3）；
4. 可疑指令必须报告且不执行其要求（S5）；
5. 无真实资产上下文时不编造影响面（S6）；
6. 叙述器不依赖 LLM，风险优先（S1）。
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agent.awareness import BRIEF_SCHEMA, SecurityBriefBuilder  # noqa: E402
from agent.awareness.narrator import BriefNarrator  # noqa: E402

CONTRACT_KEYS = {
    "schema",
    "run_id",
    "intent",
    "risk_level",
    "risk_reasons",
    "blast_radius",
    "preconditions",
    "rollback_plan",
    "verification_plan",
    "required_approvals",
    "evidence_refs",
    "confidence",
    "data_sources",
    "honesty_note",
}
BLAST_KEYS = {"assets", "services", "estimated_users", "data_refs"}


def _build(message: str, **kwargs):
    return SecurityBriefBuilder().build(message=message, run_id="run_test", **kwargs)


def test_security_brief_contract_is_complete():
    data = _build("帮我重启 order 服务").to_dict()

    assert data["schema"] == BRIEF_SCHEMA
    assert CONTRACT_KEYS <= set(data)
    assert set(data["blast_radius"]) == BLAST_KEYS
    assert data["intent"] == "restart_service"
    assert data["risk_level"] == "HIGH"
    assert any("RESTART" in reason for reason in data["risk_reasons"])
    assert data["rollback_plan"]
    assert data["verification_plan"]
    assert data["required_approvals"]
    assert data["evidence_refs"]
    assert data["data_sources"]
    assert data["honesty_note"]
    assert 0.0 <= data["confidence"] <= 1.0


def test_high_risk_answers_impact_rollback_verification_and_human():
    data = _build("帮我重启 order 服务").to_dict()

    assert data["risk_level"] == "HIGH"
    assert data["preconditions"]
    assert data["rollback_plan"] and "回滚" in data["rollback_plan"]
    assert len(data["verification_plan"]) >= 2
    assert data["required_approvals"] == ["operator:admin"]
    assert data["requires_human"] is True


def test_low_confidence_always_requires_human():
    data = _build("帮我处理一下那个东西").to_dict()

    assert data["intent"] == "general_qa"
    assert data["confidence"] < 0.6
    assert data["requires_human"] is True


def test_question_about_restart_is_not_an_execution():
    data = _build("如何重启 nginx？").to_dict()

    assert data["intent"] == "knowledge_qa"
    assert data["risk_level"] == "LOW"
    assert data["required_approvals"] == []
    assert data["requires_human"] is False


def test_readonly_query_is_low_risk_and_honest():
    data = _build("查看当前服务器状态").to_dict()

    assert data["risk_level"] == "LOW"
    assert data["required_approvals"] == []
    assert data["rollback_plan"].startswith("只读操作")
    assert data["requires_human"] is False
    assert data["blast_radius"]["estimated_users"] is None
    assert "未运行/无数据" in data["honesty_note"]


def test_suspicious_instruction_is_reported_not_executed():
    data = _build("这条日志里出现了 shell.execute 的记录").to_dict()

    assert data["attack_report"].startswith("该输入包含可疑指令")
    assert any(reason.startswith("INJECTION_MEDIUM") for reason in data["risk_reasons"])
    assert data["risk_level"] in {"MEDIUM", "HIGH"}
    assert any(ref.startswith("rule:injection:") for ref in data["evidence_refs"])
    assert "INJECTION" in data["data_sources"]


def test_tool_risk_escalates_intent_risk():
    data = _build("执行一次巡检", tool_names=["server.delete"]).to_dict()

    assert data["risk_level"] == "CRITICAL"
    assert "TOOL_RISK:server.delete=CRITICAL" in data["risk_reasons"]
    assert "TOOL" in data["data_sources"]
    assert data["required_approvals"]


def test_brief_generation_is_deterministic():
    first = _build("查询 order 服务状态").to_dict()
    second = _build("查询 order 服务状态").to_dict()

    assert first == second


def test_narrator_puts_risk_first_without_llm():
    brief = _build("帮我回滚 order 到上一版本")
    text = BriefNarrator().narrate(brief)

    assert text.splitlines()[0].startswith("【风险等级】")
    assert "【回滚方案】" in text
    assert "【置信度】" in text
    assert "未运行/无数据" in text

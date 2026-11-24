"""真实 LLM 角色代理（P2-7 / A）单元测试。

**不打真模型**：全部用 stub client，只验证协议接入、解析健壮性与弃权口径。
真实模型的实测见 `scripts/eval_debate.py --role-agent llm`（EXP-DEBATE-002）。

钉住的关键口径：
- 候选集封闭：LLM 只能选出候选集内的 top1，越界一律弃权（不猜）；
- 失败弃权：服务不可用 / 解析失败 → ``top1=None``，**不伪造**；
- 证据引用必须来自本通道视图（跨通道 id 一律过滤掉）。
"""

from __future__ import annotations

import pytest

from agent.subagents.debate import Conclusion, Rebuttal
from agent.subagents.debate_llm import (
    ABSTAIN,
    LLMRoleAgent,
    build_conclude_prompt,
    build_rebut_prompt,
    normalise_confidence,
    normalise_ids,
    normalise_top1,
    parse_json_object,
)
from agent.subagents.debate_rules import PROBE_TYPE_CANDIDATES
from agent.subagents.evidence_channels import ChannelView, EvidenceItem


class StubClient:
    """按脚本返回预置响应的假 Ollama。"""

    def __init__(self, responses: list[dict]):
        self.responses = list(responses)
        self.prompts: list[str] = []

    def generate(self, prompt: str, *, json_schema=None) -> dict:
        self.prompts.append(prompt)
        if not self.responses:
            return {"ok": False, "error": "no stub response", "text": "",
                    "latency_ms": 0.0}
        return self.responses.pop(0)

    def stats(self) -> dict:
        return {"model": "stub", "n_calls": len(self.prompts), "n_failures": 0}


def _view(*items: EvidenceItem, role: str = "log_diagnosis") -> ChannelView:
    return ChannelView(role=role, items=tuple(items))


def _agent(client: StubClient) -> LLMRoleAgent:
    return LLMRoleAgent(client)


# ============================================================ 解析与归一
def test_parse_json_object_plain():
    assert parse_json_object('{"a": 1}') == {"a": 1}


def test_parse_json_object_embedded_in_prose():
    text = '这是结果：\n```json\n{"top1": "l4-oom"}\n```\n完毕'
    assert parse_json_object(text)["top1"] == "l4-oom"


def test_parse_json_object_rejects_non_json():
    with pytest.raises(ValueError):
        parse_json_object("我觉得是内存问题")


def test_normalise_top1_accepts_candidate_and_case_insensitive():
    assert normalise_top1("l4-oom", ("l4-oom", "conf-disk")) == "l4-oom"
    assert normalise_top1("L4-OOM", ("l4-oom",)) == "l4-oom"


def test_normalise_top1_abstains_on_unknown():
    """越界答案一律弃权——不能猜，也不能当命中。"""

    assert normalise_top1("planet-x", ("l4-oom",)) is None
    assert normalise_top1(ABSTAIN, ("l4-oom",)) is None
    assert normalise_top1(None, ("l4-oom",)) is None
    assert normalise_top1("", ("l4-oom",)) is None


def test_normalise_ids_filters_out_of_channel():
    assert normalise_ids(["ev-1", "ev-9"], ("ev-1", "ev-2")) == ("ev-1",)
    assert normalise_ids("not-a-list", ("ev-1",)) == ()


def test_normalise_confidence_clamps():
    assert normalise_confidence(1.5) == 1.0
    assert normalise_confidence(-2) == 0.0
    assert normalise_confidence("x") == 0.0
    assert normalise_confidence(0.42) == pytest.approx(0.42)


# ============================================================ 提示词
def test_conclude_prompt_carries_evidence_candidates_and_guard():
    view = _view(
        EvidenceItem(evidence_id="ev-1", probe_type="oom_kills",
                     target="proc", summary="内核杀掉 java"),
        EvidenceItem(evidence_id="ev-2", probe_type="systemd_state",
                     target="svc", summary="进程反复重启"),
    )
    from agent.subagents.base import SubAgentSpec

    spec = SubAgentSpec(
        name="log_diagnosis", title="日志诊断", description="读日志",
        keywords=(), tool_names=(),
    )
    prompt = build_conclude_prompt(spec, "为什么挂了？", view, ("l4-oom",))

    assert "ev-1" in prompt and "ev-2" in prompt
    assert "l4-oom" in prompt
    assert "忽略" in prompt                      # 防提示注入声明
    assert "ABSTAIN" in prompt


def test_conclude_prompt_marks_empty_view():
    prompt = build_conclude_prompt(
        _spec(), "q", _view(), ("l4-oom",)
    )
    assert "（无证据）" in prompt


def test_rebut_prompt_shows_other_roles_and_own_previous():
    view = _view(EvidenceItem(evidence_id="ev-1", probe_type="oom_kills"))
    previous = Conclusion(role="log_diagnosis", top1="l4-oom")
    others = {
        "metric_inspector": Conclusion(
            role="metric_inspector", top1="db-redis", evidence=("ev-7",)
        )
    }
    prompt = build_rebut_prompt(_spec(), "q", view, previous, others, ("l4-oom",))
    assert "db-redis" in prompt
    assert "metric_inspector" in prompt
    assert "l4-oom" in prompt


def _spec():
    from agent.subagents.base import SubAgentSpec

    return SubAgentSpec(
        name="log_diagnosis", title="日志诊断", description="读日志",
        keywords=(), tool_names=(),
    )


# ============================================================ conclude 行为
def test_conclude_returns_normalised_conclusion():
    view = _view(EvidenceItem(evidence_id="ev-1", probe_type="oom_kills"))
    client = StubClient([
        {"ok": True, "text": '{"top1": "l4-oom", "candidates": ["l4-oom"], '
                              '"evidence": ["ev-1"], "confidence": 0.8, '
                              '"rationale": "内核 OOM"}',
         "latency_ms": 10.0},
    ])
    conclusion = _agent(client).conclude("log_diagnosis", "q", view)

    assert isinstance(conclusion, Conclusion)
    assert conclusion.top1 == "l4-oom"
    assert conclusion.evidence == ("ev-1",)
    assert conclusion.confidence == pytest.approx(0.8)


def test_conclude_filters_cross_channel_evidence():
    view = _view(EvidenceItem(evidence_id="ev-1", probe_type="oom_kills"))
    client = StubClient([
        {"ok": True, "text": '{"top1": "l4-oom", "candidates": [], '
                              '"evidence": ["ev-99", "ev-1"], "confidence": 0.5, '
                              '"rationale": ""}', "latency_ms": 10.0},
    ])
    conclusion = _agent(client).conclude("log_diagnosis", "q", view)
    assert conclusion.evidence == ("ev-1",)


def test_conclude_abstains_when_service_fails():
    client = StubClient([
        {"ok": False, "error": "HTTP 500", "text": "", "latency_ms": 1.0},
    ])
    agent = _agent(client)
    conclusion = agent.conclude("log_diagnosis", "q", _view())

    assert conclusion.top1 is None
    assert "HTTP 500" in conclusion.rationale
    assert agent.n_parse_failures >= 1


def test_conclude_abstains_on_unparsable_output():
    client = StubClient([
        {"ok": True, "text": "我认为是内存问题，无法给出 JSON。", "latency_ms": 1.0},
    ])
    agent = _agent(client)
    conclusion = agent.conclude("log_diagnosis", "q", _view())
    assert conclusion.top1 is None


def test_conclude_abstains_when_top1_outside_candidates():
    """模型编了一个候选集外的根因 → 弃权，不算命中。"""

    view = _view(EvidenceItem(evidence_id="ev-1", probe_type="oom_kills"))
    client = StubClient([
        {"ok": True, "text": '{"top1": "磁盘坏了", "candidates": [], '
                              '"evidence": [], "confidence": 0.9, "rationale": ""}',
         "latency_ms": 1.0},
    ])
    conclusion = _agent(client).conclude("log_diagnosis", "q", view)
    assert conclusion.top1 is None
    assert conclusion.candidates == ()


# ============================================================ rebut 行为
def test_rebut_revises_top1():
    view = _view(EvidenceItem(evidence_id="ev-1", probe_type="oom_kills"))
    previous = Conclusion(role="log_diagnosis", top1="l4-oom")
    others = {"metric_inspector": Conclusion(role="metric_inspector", top1="conf-disk")}
    client = StubClient([
        {"ok": True, "text": '{"agree_with": null, "dispute": "时间线不符", '
                              '"new_evidence": ["ev-1"], "revised_top1": "l4-oom", '
                              '"rationale": "维持"}', "latency_ms": 1.0},
    ])
    rebuttal = _agent(client).rebut("log_diagnosis", "q", view, others, previous)
    assert isinstance(rebuttal, Rebuttal)
    assert rebuttal.revised_top1 == "l4-oom"
    assert rebuttal.new_evidence == ("ev-1",)


def test_rebut_holds_previous_on_failure():
    view = _view()
    previous = Conclusion(role="log_diagnosis", top1="l4-oom")
    client = StubClient([
        {"ok": False, "error": "连接超时", "text": "", "latency_ms": 1.0},
    ])
    rebuttal = _agent(client).rebut("log_diagnosis", "q", view, {}, previous)
    assert rebuttal.revised_top1 == "l4-oom"      # 失败时维持原结论
    assert "连接超时" in rebuttal.dispute


def test_rebut_ignores_unknown_agree_role():
    view = _view()
    previous = Conclusion(role="log_diagnosis", top1=None)
    client = StubClient([
        {"ok": True, "text": '{"agree_with": "ghost", "dispute": "", '
                              '"new_evidence": [], "revised_top1": "ABSTAIN", '
                              '"rationale": ""}', "latency_ms": 1.0},
    ])
    rebuttal = _agent(client).rebut("log_diagnosis", "q", view, {}, previous)
    assert rebuttal.agree_with is None


# ============================================================ 候选集
def test_candidates_for_is_union_of_probe_type_candidates():
    view = _view(
        EvidenceItem(evidence_id="e1", probe_type="oom_kills"),
        EvidenceItem(evidence_id="e2", probe_type="memory"),
    )
    names = _agent(StubClient([])).candidates_for(view)
    assert set(names) == {"l4-oom"}
    assert PROBE_TYPE_CANDIDATES["oom_kills"] == ("l4-oom",)


def test_candidates_for_empty_view_is_empty():
    assert _agent(StubClient([])).candidates_for(_view()) == ()


def test_stats_report_failures_and_model():
    agent = _agent(StubClient([]))
    agent.n_abstain = 3
    agent.n_parse_failures = 1
    stats = agent.stats()
    assert stats["n_abstain"] == 3
    assert stats["n_parse_or_call_failures"] == 1
    assert "model" in stats


def test_unknown_role_raises():
    with pytest.raises(KeyError):
        _agent(StubClient([])).role_spec("ghost")


def test_coverage_oracle_role_gets_synthetic_spec():
    """覆盖对照不是通道角色，但必须能复用同一结论接口。"""

    spec = _agent(StubClient([])).role_spec("_coverage_oracle")
    assert spec.name == "_coverage_oracle"
    assert spec.title


def test_ollama_client_disables_thinking_by_default(monkeypatch):
    """qwen3 等思考型模型默认会把 num_predict 耗在思考上、正文为空。

    因此客户端**必须**默认下发 ``think=False``；否则评测会得到「全量解析失败」
    的假象（实测 104/104 次空响应）。
    """

    captured: dict = {}

    class _Resp:
        status_code = 200
        text = "{}"

        def json(self):
            return {"response": '{"top1": null}', "eval_count": 5}

    def _fake_post(url, json=None, timeout=None):
        captured.update(json)
        return _Resp()

    monkeypatch.setattr("agent.subagents.debate_llm.httpx.post", _fake_post)

    from agent.subagents.debate_llm import OllamaClient

    client = OllamaClient()
    assert client.think is False
    result = client.generate("ping", json_schema={"type": "object"})
    assert result["ok"] is True
    assert captured["think"] is False
    assert captured["stream"] is False
    assert client.stats()["think"] is False


def test_ollama_client_can_opt_into_thinking(monkeypatch):
    """显式开启思考时应如实下发，便于对照复现。"""

    captured: dict = {}

    class _Resp:
        status_code = 200
        text = "{}"

        def json(self):
            return {"response": '{"top1": null}'}

    monkeypatch.setattr(
        "agent.subagents.debate_llm.httpx.post",
        lambda url, json=None, timeout=None: (captured.update(json), _Resp())[1],
    )

    from agent.subagents.debate_llm import OllamaClient

    OllamaClient(think=True).generate("ping")
    assert captured["think"] is True

"""W7 事件驱动触发端点的门禁与写回口径。

覆盖：内部令牌 fail-closed、只读白名单、模型不可用不产事件、
真实诊断计入 agent_run 账本。
"""

import pytest
from fastapi import HTTPException

from app.api import agent_trigger as trigger_module
from app.core.config import settings
from app.services.agent_runtime import AgentRunResult

TOKEN = "trigger-internal-token"
PATH = "/api/agent/trigger"


def _payload() -> dict:
    return {
        "alertId": 42,
        "taskId": 7,
        "resourceKey": "task:7",
        "ownerUserId": "81",
        "severity": "P1",
        "metric": "cpu",
        "observed": "95",
        "threshold": "cpu>90",
        "title": "web-prod：cpu>90",
    }


@pytest.fixture
def internal_headers(monkeypatch):
    monkeypatch.setattr(settings, "memory_internal_token", TOKEN)
    return {"X-SmartOps-Internal-Token": TOKEN}


def _patch_probe(monkeypatch, available: bool, detail: str = "") -> None:
    async def fake_probe(**_kwargs):
        return available, detail

    monkeypatch.setattr(trigger_module.model_probe, "probe_llm_availability", fake_probe)


def _patch_ledger(monkeypatch) -> list:
    calls: list = []

    async def fake_record(self, result, *, goal=""):
        calls.append(result.run_id)
        return {"recorded": True, "runId": result.run_id}

    monkeypatch.setattr(trigger_module.RunLedgerRecorder, "record", fake_record)
    return calls


def test_trigger_requires_configured_token(client, monkeypatch):
    monkeypatch.setattr(settings, "memory_internal_token", "")

    response = client.post(PATH, json=_payload())

    assert response.status_code == 503


def test_trigger_rejects_missing_or_wrong_token(client, internal_headers):
    assert client.post(PATH, json=_payload()).status_code == 401

    wrong = {"X-SmartOps-Internal-Token": "not-the-token"}
    assert client.post(PATH, json=_payload(), headers=wrong).status_code == 403


def test_model_unavailable_creates_no_event_and_skips_ledger(client, internal_headers, monkeypatch):
    _patch_probe(monkeypatch, False, "LLM_PROVIDER_MOCK")
    ledger_calls = _patch_ledger(monkeypatch)

    response = client.post(PATH, json=_payload(), headers=internal_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["created"] is False
    assert body["modelAvailable"] is False
    assert body["reason"] == "MODEL_UNAVAILABLE"
    assert ledger_calls == []


def test_trigger_returns_diagnosis_and_records_ledger(client, internal_headers, monkeypatch):
    _patch_probe(monkeypatch, True)
    ledger_calls = _patch_ledger(monkeypatch)
    seen: dict = {}

    def fake_run(payload):
        seen["user_id"] = payload.owner_user_id
        return AgentRunResult(
            status="completed",
            request_id="req-1",
            user_id=payload.owner_user_id or "system",
            run_id="run-1",
            answer="只读初诊：CPU 持续高位，建议先核对近期变更。",
            reason="",
            brief={"narrative": "证据来自告警面与知识检索"},
            tool_calls=[
                {"toolName": "sentinel.alerts", "success": True},
                {"toolName": "knowledge.search", "success": True},
            ],
        )

    monkeypatch.setattr(trigger_module, "_run_diagnosis", fake_run)

    response = client.post(PATH, json=_payload(), headers=internal_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["created"] is True
    assert body["modelAvailable"] is True
    assert body["runId"] == "run-1"
    assert body["brief"]["narrative"]
    assert ledger_calls == ["run-1"]
    assert seen["user_id"] == "81"


def test_trigger_does_not_create_event_when_plan_failed(client, internal_headers, monkeypatch):
    _patch_probe(monkeypatch, True)
    _patch_ledger(monkeypatch)

    def fake_run(payload):
        return AgentRunResult(
            status="completed",
            request_id="req-2",
            user_id=payload.owner_user_id or "system",
            run_id="run-2",
            answer="计划执行结束：completed，成功 0/2 步。",
            tool_calls=[{"toolName": "sentinel.alerts", "success": False}],
        )

    monkeypatch.setattr(trigger_module, "_run_diagnosis", fake_run)

    body = client.post(PATH, json=_payload(), headers=internal_headers).json()

    assert body["created"] is False


def test_trigger_steps_only_use_read_whitelist():
    payload = trigger_module.AgentTriggerRequest.model_validate(_payload())

    steps = trigger_module.build_trigger_steps(payload)

    names = {step["tool_name"] for step in steps}
    assert names <= trigger_module.TRIGGER_READ_TOOLS
    assert "sentinel.metrics" not in names
    alerts = next(step for step in steps if step["tool_name"] == "sentinel.alerts")
    assert alerts["arguments"] == {"taskId": 7}


def test_trigger_steps_include_metrics_when_server_id_present():
    data = _payload()
    data["serverId"] = 3
    payload = trigger_module.AgentTriggerRequest.model_validate(data)

    names = [step["tool_name"] for step in trigger_module.build_trigger_steps(payload)]

    assert "sentinel.metrics" in names


def test_validate_tool_names_rejects_write_tools():
    with pytest.raises(HTTPException) as error:
        trigger_module.validate_tool_names(["inspector.event.report"])

    assert error.value.status_code == 400

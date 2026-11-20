"""编排服务入口的接口测试（不加载真实模型）。"""

from fastapi.testclient import TestClient

from app.api import orchestrate as orchestrate_api
from app.core.config import settings
from app.main import app


class _FakePlan:
    def to_dict(self) -> dict:
        return {
            "goal": "巡检 A 区",
            "overall_status": "SUCCESS",
            "subtasks": [{"task_id": "t_patrol_planner"}],
            "results": [],
            "trace_id": "trace-test",
            "metrics": {},
        }


class _FakeOrchestrator:
    def orchestrate(self, goal, context=None, enable_agents=None, exclude_agents=None):
        plan = _FakePlan()
        plan.goal = goal
        return plan


def _client(monkeypatch) -> TestClient:
    monkeypatch.setattr(settings, "memory_internal_token", "test-token")
    monkeypatch.setattr(orchestrate_api, "_build_orchestrator", lambda bus, max_concurrency: _FakeOrchestrator())
    return TestClient(app)


def test_orchestrate_requires_token(monkeypatch):
    client = _client(monkeypatch)
    response = client.post("/api/orchestrate", json={"goal": "巡检 A 区"})
    assert response.status_code == 403


def test_orchestrate_returns_plan(monkeypatch):
    client = _client(monkeypatch)
    response = client.post(
        "/api/orchestrate",
        json={"goal": "巡检 A 区", "context": {"device_key": "robot-car-01"}},
        headers={"X-Internal-Token": "test-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["overall_status"] == "SUCCESS"
    assert body["subtasks"][0]["task_id"] == "t_patrol_planner"


def test_orchestrate_stream_emits_result(monkeypatch):
    client = _client(monkeypatch)
    with client.stream(
        "GET",
        "/api/orchestrate/stream",
        params={"goal": "巡检 A 区"},
        headers={"X-Internal-Token": "test-token"},
    ) as response:
        assert response.status_code == 200
        text = "".join(response.iter_text())
    assert "event: open" in text
    assert '"event": "result"' in text
    assert "trace-test" in text

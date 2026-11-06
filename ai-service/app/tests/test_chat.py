def test_chat(client, auth_headers):

    response = client.post(
        "/api/chat",
        headers=auth_headers(),
        json={
            "message": "如何检查 nginx 状态？",
            "use_rag": False,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert "answer" in data

    assert "conversation_id" in data

    assert data["provider"] == "mock"

    assert data["model"] == "mock-model"


def test_chat_validation(client, auth_headers):

    response = client.post(
        "/api/chat",
        headers=auth_headers(),
        json={
            "message": "",
        },
    )

    assert response.status_code == 422


def test_chat_marks_degraded_provider(client, monkeypatch, auth_headers):
    from app.core.config import settings
    from app.services.llm import LLMService

    async def unavailable(self, **kwargs):
        raise ConnectionError("test Ollama connection failure")

    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(LLMService, "_ollama_generate", unavailable)

    response = client.post(
        "/api/chat",
        headers=auth_headers(),
        json={"message": "降级标记", "use_rag": False},
    )

    assert response.status_code == 200
    metadata = response.json()["metadata"]
    assert metadata["degraded"] is True
    assert metadata["effective_provider"] == "mock"


def test_chat_runs_inspector_and_returns_rejected_false_success(client, auth_headers):
    response = client.post(
        "/api/chat",
        headers=auth_headers(),
        json={
            "message": "检查任务状态",
            "use_rag": False,
            "metadata": {
                "agent_claim": "任务已解决，服务恢复正常",
                "actual_state": {"probes": [{"probe_type": "http", "status_code": 502}]},
            },
        },
    )

    assert response.status_code == 200
    inspection = response.json()["metadata"]["inspection"]
    assert inspection["status"] == "REJECTED"
    assert inspection["verification_result"]["false_success"] is True

"""Knowledge Service correlation contract: echo headers + structured log."""

import logging

import pytest
from fastapi.testclient import TestClient

from knowledge import server
from knowledge.service import KnowledgeService


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("KNOWLEDGE_API_KEY", raising=False)
    monkeypatch.delenv("KNOWLEDGE_ALLOW_INGEST", raising=False)
    monkeypatch.setenv("KNOWLEDGE_ALLOW_ANONYMOUS", "true")
    monkeypatch.setattr(server, "service", KnowledgeService())
    # SEC-12：匿名模式仅回环客户端可用，测试显式以回环来源访问。
    return TestClient(server.app, client=("127.0.0.1", 51234))


def test_search_echoes_and_logs_correlation_ids(client, caplog):
    caplog.set_level(logging.INFO, logger="knowledge.server")
    headers = {
        "X-Request-ID": "req-kb-1",
        "X-Task-ID": "task-kb-1",
        "X-Run-ID": "run-kb-1",
    }

    response = client.post(
        "/api/search",
        json={"query": "nginx"},
        headers=headers,
    )

    assert response.status_code == 200
    for name, value in headers.items():
        assert response.headers[name] == value
    assert "request_id=req-kb-1" in caplog.text
    assert "task_id=task-kb-1" in caplog.text
    assert "run_id=run-kb-1" in caplog.text
    assert "status=ok" in caplog.text
    assert "nginx" not in caplog.text


def test_search_without_correlation_keeps_working(client):
    response = client.post("/api/search", json={"query": "nginx"})
    assert response.status_code == 200
    assert "X-Request-ID" not in response.headers


def test_invalid_correlation_ids_are_not_echoed(client):
    response = client.post(
        "/api/search",
        json={"query": "nginx"},
        headers={"X-Request-ID": "bad id", "X-Run-ID": "x" * 120},
    )

    assert response.status_code == 200
    assert "X-Request-ID" not in response.headers
    assert "X-Run-ID" not in response.headers

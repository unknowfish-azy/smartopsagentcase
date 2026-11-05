from fastapi.testclient import TestClient
import pytest

from knowledge import server
from knowledge.service import KnowledgeService


@pytest.fixture
def client(monkeypatch):
    """隔离实例 + 清空鉴权相关环境变量，避免依赖本机配置。"""
    monkeypatch.delenv("KNOWLEDGE_API_KEY", raising=False)
    monkeypatch.delenv("KNOWLEDGE_ALLOW_INGEST", raising=False)
    monkeypatch.setattr(server, "service", KnowledgeService())
    return TestClient(server.app)


DOCUMENT = {"content": "nginx 检查 systemctl status nginx", "source": "test.md"}


def test_search_stays_open_without_key(client):
    response = client.post("/api/search", json={"query": "nginx"})
    assert response.status_code == 200


def test_ingestion_is_closed_by_default(client):
    response = client.post("/api/documents", json=DOCUMENT)
    assert response.status_code == 403
    assert "KNOWLEDGE_ALLOW_INGEST" in response.json()["detail"]


def test_ingestion_can_be_enabled_for_local_use(client, monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_ALLOW_INGEST", "1")
    response = client.post("/api/documents", json=DOCUMENT)
    assert response.status_code == 200
    assert response.json()["added"] > 0


@pytest.mark.parametrize("path,payload", [
    ("/api/search", {"query": "nginx"}),
    ("/api/documents", DOCUMENT),
])
def test_key_is_enforced_on_every_endpoint(client, monkeypatch, path, payload):
    monkeypatch.setenv("KNOWLEDGE_API_KEY", "s3cret")

    missing = client.post(path, json=payload)
    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "X-API-Key"

    wrong = client.post(path, json=payload, headers={"X-API-Key": "wrong"})
    assert wrong.status_code == 401

    ok = client.post(path, json=payload, headers={"X-API-Key": "s3cret"})
    assert ok.status_code == 200


def test_valid_key_allows_ingestion_even_when_open_ingest_is_off(client, monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_API_KEY", "s3cret")
    response = client.post(
        "/api/documents",
        json=DOCUMENT,
        headers={"X-API-Key": "s3cret"},
    )
    assert response.status_code == 200
    assert response.json()["total_chunks"] > 0


def test_health_reports_whether_auth_is_required(client, monkeypatch):
    assert client.get("/api/health").json()["auth_required"] is False
    monkeypatch.setenv("KNOWLEDGE_API_KEY", "s3cret")
    assert client.get("/api/health").json()["auth_required"] is True

from fastapi.testclient import TestClient
import pytest

from knowledge import server
from knowledge.service import KnowledgeService


@pytest.fixture
def client(monkeypatch):
    """隔离实例 + 清空鉴权相关环境变量（默认场景 = 未配置 key 且未允许匿名）。"""
    monkeypatch.delenv("KNOWLEDGE_API_KEY", raising=False)
    monkeypatch.delenv("KNOWLEDGE_ALLOW_INGEST", raising=False)
    monkeypatch.delenv("KNOWLEDGE_ALLOW_ANONYMOUS", raising=False)
    monkeypatch.setattr(server, "service", KnowledgeService())
    return TestClient(server.app)


@pytest.fixture
def loopback_client(monkeypatch):
    """显式匿名模式 + 回环客户端（本机使用的合法形态）。"""
    monkeypatch.delenv("KNOWLEDGE_API_KEY", raising=False)
    monkeypatch.delenv("KNOWLEDGE_ALLOW_INGEST", raising=False)
    monkeypatch.setenv("KNOWLEDGE_ALLOW_ANONYMOUS", "true")
    monkeypatch.setattr(server, "service", KnowledgeService())
    return TestClient(server.app, client=("127.0.0.1", 51234))


DOCUMENT = {"content": "nginx 检查 systemctl status nginx", "source": "test.md"}


def test_search_fail_closed_without_key_or_anonymous(client):
    """SEC-12：未配置 key 且未显式允许匿名 → 拒绝（503 fail-closed），不是 200。"""
    response = client.post("/api/search", json={"query": "nginx"})
    assert response.status_code == 503
    assert "KNOWLEDGE_API_KEY" in response.json()["detail"]


def test_anonymous_mode_allows_loopback_search(loopback_client):
    response = loopback_client.post("/api/search", json={"query": "nginx"})
    assert response.status_code == 200


def test_anonymous_mode_rejects_non_loopback(client, monkeypatch):
    """匿名模式即便绑定 0.0.0.0，非回环客户端也被应用层拒绝（默认 TestClient host 非
    回环，用它模拟外部来源）。"""
    monkeypatch.setenv("KNOWLEDGE_ALLOW_ANONYMOUS", "true")
    response = client.post("/api/search", json={"query": "nginx"})
    assert response.status_code == 403


def test_ingestion_never_accepts_anonymous(loopback_client, monkeypatch):
    """SEC-12：摄入永不匿名——即使显式匿名模式 + 回环 + ALLOW_INGEST=1 也拒绝。"""
    monkeypatch.setenv("KNOWLEDGE_ALLOW_INGEST", "1")
    response = loopback_client.post("/api/documents", json=DOCUMENT)
    assert response.status_code == 403
    assert "KNOWLEDGE_API_KEY" in response.json()["detail"]


def test_ingestion_is_closed_by_default(client):
    response = client.post("/api/documents", json=DOCUMENT)
    assert response.status_code == 403
    assert "KNOWLEDGE_API_KEY" in response.json()["detail"]


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


def test_health_reports_auth_mode(client, monkeypatch):
    body = client.get("/api/health").json()
    assert body["auth_required"] is False
    assert body["auth_mode"] == "misconfigured_fail_closed"

    monkeypatch.setenv("KNOWLEDGE_API_KEY", "s3cret")
    body = client.get("/api/health").json()
    assert body["auth_required"] is True
    assert body["auth_mode"] == "api_key"

    monkeypatch.delenv("KNOWLEDGE_API_KEY", raising=False)
    monkeypatch.setenv("KNOWLEDGE_ALLOW_ANONYMOUS", "true")
    body = client.get("/api/health").json()
    assert body["auth_required"] is False
    assert body["auth_mode"] == "anonymous_loopback_only"

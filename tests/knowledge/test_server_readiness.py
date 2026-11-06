from fastapi.testclient import TestClient
import pytest

from knowledge import server
from knowledge.service import KnowledgeService


@pytest.fixture
def empty_service(monkeypatch):
    instance = KnowledgeService()
    monkeypatch.setattr(server, "service", instance)
    # SEC-12：摄入永不匿名，本地测试统一走 API key。
    monkeypatch.setenv("KNOWLEDGE_API_KEY", "test-key")
    return instance


def test_empty_index_is_alive_but_not_ready(empty_service):
    client = TestClient(server.app)
    assert client.get("/api/health").status_code == 200
    response = client.get("/api/ready")
    assert response.status_code == 503
    assert response.json()["ready"] is False
    assert response.json()["reason"] == "empty_index"


def test_health_alias_matches_api_health(empty_service):
    # 探针工具常用 /health，保持与 /api/health 同内容。
    client = TestClient(server.app)
    assert client.get("/health").json() == client.get("/api/health").json()


def test_health_exposes_embedding_backend(empty_service):
    """默认后端为 bge 时，健康检查必须如实暴露实际后端与维度，
    避免回退到 hash 后无人察觉。"""
    client = TestClient(server.app)
    embedding = client.get("/api/health").json()["embedding"]
    assert embedding["backend_requested"] in ("bge", "hash")
    assert embedding["backend_actual"] in ("bge", "hash")
    assert isinstance(embedding["dimension"], int)
    # requested 与 actual 不一致时必须有回退原因
    if embedding["backend_requested"] != embedding["backend_actual"]:
        assert embedding["fallback_reason"]


def test_ingestion_changes_readiness_without_restart(empty_service):
    client = TestClient(server.app)
    assert client.get("/api/ready").status_code == 503
    response = client.post(
        "/api/documents",
        json={"content": "nginx 检查 systemctl status nginx", "source": "test.md"},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    ready = client.get("/api/ready")
    assert ready.status_code == 200
    assert ready.json()["ready"] is True
    assert ready.json()["chunks"] > 0
    assert ready.json()["instance_id"]


@pytest.mark.parametrize("mode,expected", [("disabled", "disabled"), ("missing", "missing"), ("empty", "empty"), ("loaded", "loaded")])
def test_seed_summary_is_explicit_and_reproducible(empty_service, monkeypatch, tmp_path, mode, expected):
    root = tmp_path / "corpus"
    if mode != "missing":
        root.mkdir()
    if mode == "loaded":
        (root / "ops.md").write_text("nginx operational guide", encoding="utf-8")
    monkeypatch.setenv("KNOWLEDGE_REFERENCE_DIR", str(root))
    monkeypatch.setenv("KNOWLEDGE_SEED_REFERENCE", "0" if mode == "disabled" else "1")
    summary = server._seed_reference_corpus()
    assert summary["status"] == expected
    assert summary["documents"] == (1 if mode == "loaded" else 0)
    if mode == "loaded":
        assert len(summary["corpus_sha256"]) == 64
        assert empty_service.chunk_count > 0
    assert str(root) not in str(summary)

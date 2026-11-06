"""SEC-01 / SEC-02 negative examples: chat requires a signed, single-use run token."""
import time

from app.tests.conftest import issue_run_token


def test_chat_without_token_is_rejected(client):
    response = client.post("/api/chat", json={"message": "hello", "use_rag": False})

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "RUN_TOKEN_REQUIRED"


def test_stream_without_token_is_rejected(client):
    response = client.post("/api/chat/stream", json={"message": "hello", "use_rag": False})

    assert response.status_code == 401


def test_token_signed_with_another_secret_is_rejected(client):
    forged = issue_run_token(secret="another-secret-0123456789abcdef")
    response = client.post("/api/chat", json={"message": "hello", "use_rag": False},
                           headers={"X-Run-Token": forged})

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "RUN_TOKEN_INVALID"


def test_expired_token_is_rejected(client):
    expired = issue_run_token(ttl=-10)
    response = client.post("/api/chat", json={"message": "hello", "use_rag": False},
                           headers={"X-Run-Token": expired})

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "RUN_TOKEN_EXPIRED"


def test_unconfigured_secret_fails_closed(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "chat_run_token_secret", "")

    response = client.post("/api/chat", json={"message": "hello", "use_rag": False})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "CHAT_RUN_TOKEN_NOT_CONFIGURED"


def test_client_supplied_run_id_is_ignored(client, run_token):
    token = run_token(run_id="run-server-issued")
    response = client.post(
        "/api/chat",
        json={"message": "hello", "use_rag": False},
        headers={"X-Run-Token": token, "X-Run-ID": "run-attacker-controlled"},
    )

    assert response.status_code == 200
    event = response.json()["metadata"]["run_event"]
    assert event["run_id"] == "run-server-issued"
    assert response.headers["X-Run-ID"] == "run-server-issued"


def test_reusing_a_token_is_rejected(client, run_token):
    token = run_token()

    first = client.post("/api/chat", json={"message": "hello", "use_rag": False},
                        headers={"X-Run-Token": token})
    second = client.post("/api/chat", json={"message": "other", "use_rag": False},
                         headers={"X-Run-Token": token})

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "RUN_TOKEN_REPLAYED"


def test_expired_token_boundary_uses_server_clock():
    # 纯函数边界：exp <= now 即拒绝，避免"宽限窗口"被当成可用令牌。
    from app.core.run_token import RunTokenError, verify_run_token

    token = issue_run_token(ttl=-1)
    try:
        verify_run_token(token, "test-run-token-secret-0123456789", now=time.time())
    except RunTokenError as failure:
        assert failure.code == "RUN_TOKEN_EXPIRED"
    else:  # pragma: no cover - a passing window would be a security regression
        raise AssertionError("expired token was accepted")

import base64
import hashlib
import hmac
import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app


TEST_RUN_TOKEN_SECRET = "test-run-token-secret-0123456789"


@pytest.fixture(autouse=True)
def isolated_model_settings(monkeypatch):
    """Unit tests must not inherit a developer's live model configuration."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(settings, "llm_model", "mock-model")


@pytest.fixture(autouse=True)
def chat_auth_settings(monkeypatch):
    """SEC-01：测试默认走令牌校验，显式匿名模式只由单个用例自行打开。"""
    from app.core.config import settings
    monkeypatch.setattr(settings, "chat_run_token_secret", TEST_RUN_TOKEN_SECRET)
    monkeypatch.setattr(settings, "chat_allow_anonymous", False)


@pytest.fixture
def client():
    return TestClient(app)


def issue_run_token(subject: str = "1", run_id: str | None = None, ttl: int = 300,
                    secret: str = TEST_RUN_TOKEN_SECRET) -> str:
    """Build the same format as com.smartops.security.RunTokenService."""
    now = int(time.time())
    payload = {
        "sub": subject,
        "run": run_id or f"run-{uuid.uuid4().hex}",
        "iat": now,
        "exp": now + ttl,
    }
    body = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("utf-8").rstrip("=")
    signature = base64.urlsafe_b64encode(
        hmac.new(secret.encode("utf-8"), f"v1.{body}".encode("utf-8"), hashlib.sha256).digest()
    ).decode("utf-8").rstrip("=")
    return f"v1.{body}.{signature}"


@pytest.fixture
def run_token():
    return issue_run_token


@pytest.fixture
def auth_headers(run_token):
    def build(**kwargs):
        return {"X-Run-Token": run_token(**kwargs)}
    return build

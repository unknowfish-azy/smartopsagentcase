import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(autouse=True)
def isolated_model_settings(monkeypatch):
    """Unit tests must not inherit a developer's live model configuration."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(settings, "llm_model", "mock-model")


@pytest.fixture
def client():
    return TestClient(app)

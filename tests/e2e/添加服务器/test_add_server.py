"""Live anonymous boundary. Real create/list/delete uses isolated Spring/H2 tests."""
import pytest

@pytest.mark.e2e
def test_anonymous_add_server_is_forbidden(http_client, require_backend):
    response = http_client.post(require_backend + "/api/servers", json={"name": "anonymous-contract", "host": "127.0.0.1", "port": 22})
    assert response.status_code == 403
    assert http_client.get(require_backend + "/api/servers").status_code == 401

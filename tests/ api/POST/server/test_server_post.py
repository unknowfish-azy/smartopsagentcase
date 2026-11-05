"""Anonymous writes without CSRF are forbidden; never insert into the live DB."""
import pytest

@pytest.mark.parametrize("payload", [{"name": "anonymous-contract", "host": "127.0.0.1", "port": 22}, {}, {"name": "anonymous-contract", "host": "127.0.0.1", "port": -1}])
def test_anonymous_server_writes_require_csrf(http_client, require_backend, payload):
    assert http_client.post(require_backend + "/api/servers", json=payload).status_code == 403

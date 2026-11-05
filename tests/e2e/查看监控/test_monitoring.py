"""Live anonymous monitoring boundary; seeded success is tested in isolated H2."""
import pytest

@pytest.mark.e2e
def test_anonymous_monitoring_is_unauthorized(http_client, require_backend):
    assert http_client.get(require_backend + "/api/servers").status_code == 401
    assert http_client.get(require_backend + "/api/servers/1/metrics/latest").status_code == 401

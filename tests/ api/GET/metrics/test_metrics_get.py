"""Anonymous metric access is rejected before resource lookup."""
import pytest

@pytest.mark.parametrize("path", ["/api/servers/1/metrics/latest", "/api/servers/1/metrics?page=1&size=20", "/api/servers/0/metrics/latest", "/api/servers/-1/metrics/latest", "/api/servers/999999999/metrics/latest"])
def test_anonymous_metrics_are_unauthorized(http_client, require_backend, path):
    assert http_client.get(require_backend + path).status_code == 401

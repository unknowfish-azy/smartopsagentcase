"""Live anonymous contract; authenticated success lives in ServerAuthenticationContractIntegrationTest."""
import pytest

@pytest.mark.parametrize("path", ["/api/servers", "/api/servers/999999999", "/api/servers?page=1&size=10", "/api/servers?page=1&size=20", "/api/servers?page=1&size=50"])
def test_anonymous_server_reads_are_unauthorized(http_client, require_backend, path):
    assert http_client.get(require_backend + path).status_code == 401

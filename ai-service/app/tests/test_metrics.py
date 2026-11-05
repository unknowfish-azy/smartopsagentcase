"""PERF-08：/metrics 必须是真实可抓取的出口，而不是配置里的一个空路径。"""

from fastapi.testclient import TestClient

from app.main import app


def test_metrics_endpoint_exposes_real_http_metrics():
    client = TestClient(app)
    client.get("/api/health")

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    body = response.text
    # 指标来自中间件真实计数，而不是静态文本
    assert "smartops_ai_http_requests_total" in body
    assert 'path="/api/health"' in body
    assert "smartops_ai_build_info" in body

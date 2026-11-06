"""N03：只读探针登记边界与有界 GET 执行器测试（不访问外网、不启动服务）。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from agent.recovery_contracts import (
    Probe,
    ProbeDeadlineError,
    ProbeExecutor,
    ProbeRegistrationError,
    ProbeRequest,
    ProbeRegistry,
    Target,
    TransportResponse,
    loopback_endpoint,
    parse_time,
    payload_digest,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DECISION = "2026-11-05T02:00:00Z"


def _case(name: str = "positive") -> dict:
    return json.loads((FIXTURES / f"vp01-{name}.json").read_text(encoding="utf-8"))


def _probe(**overrides) -> Probe:
    base = {
        "probe_id": "probe-a",
        "collector_id": "col-a",
        "collector_version": "1.0.0",
        "obligation_ids": ("obl-business-health",),
        "cost": 1,
        "permission": "probe:read",
        "read_only": True,
        "endpoint": loopback_endpoint(18081),
        "path": "/health",
        "target_id": "service:edge-nginx",
        "source_group": "sg-a",
    }
    base.update(overrides)
    return Probe(**base)


class FakeClock:
    """可注入逻辑时钟；transport 可在返回前推进它来模拟 slow-drip。"""

    def __init__(self, now: datetime | str = DECISION) -> None:
        self.current = parse_time(now)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, milliseconds: int) -> None:
        self.current = self.current + timedelta(milliseconds=milliseconds)


class FakeTransport:
    def __init__(
        self,
        response: TransportResponse,
        *,
        clock: FakeClock | None = None,
        advance_ms: int = 0,
    ) -> None:
        self.response = response
        self.clock = clock
        self.advance_ms = advance_ms
        self.requests: list[ProbeRequest] = []

    def __call__(self, request: ProbeRequest) -> TransportResponse:
        self.requests.append(request)
        if self.clock is not None:
            self.clock.advance(self.advance_ms)
        return self.response


def _executor(
    response: TransportResponse,
    *,
    clock: FakeClock | None = None,
    advance_ms: int = 0,
) -> tuple[ProbeExecutor, FakeTransport, FakeClock]:
    clock = clock or FakeClock()
    transport = FakeTransport(response, clock=clock, advance_ms=advance_ms)
    return ProbeExecutor(transport=transport, clock=clock), transport, clock


# ---------------------------------------------------------------------------
# 登记校验
# ---------------------------------------------------------------------------

def test_valid_probe_registers_and_registry_orders_by_probe_id():
    registry = ProbeRegistry()
    registry.register(_probe(probe_id="probe-b", collector_id="col-b", source_group="sg-b"))
    registry.register(_probe(probe_id="probe-a"))
    assert [probe.probe_id for probe in registry.probes()] == ["probe-a", "probe-b"]
    assert len(registry) == 2
    assert registry.get("probe-a").read_only is True


def test_duplicate_probe_id_is_rejected():
    registry = ProbeRegistry()
    registry.register(_probe())
    with pytest.raises(ProbeRegistrationError, match="重复"):
        registry.register(_probe())


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"read_only": False}, "read_only"),
        ({"obligation_ids": ()}, "至少一个"),
        ({"obligation_ids": ("obl-1", "obl-1")}, "不得重复"),
        ({"cost": 0}, "cost"),
        ({"cost": -1}, "cost"),
        ({"permission": ""}, "permission"),
        ({"endpoint": "http://example.com:18081"}, "主机"),
        ({"endpoint": "http://127.0.0.1:18081/health"}, "不能自带路径"),
        ({"endpoint": "http://127.0.0.1:18081?x=1"}, "查询串"),
        ({"endpoint": "http://127.0.0.1:0"}, "端口"),
        ({"endpoint": "https://127.0.0.1:18081"}, "只允许 http"),
        ({"path": "/admin"}, "固定允许"),
        ({"path": "http://127.0.0.1:18081/health"}, "固定允许"),
        ({"probe_id": "bad id"}, "合法标识"),
        ({"target_id": ""}, "target_id"),
    ],
)
def test_registration_rejects_invalid_probe(overrides: dict, match: str):
    registry = ProbeRegistry()
    with pytest.raises(ProbeRegistrationError, match=match):
        registry.register(_probe(**overrides))


def test_loopback_endpoint_rejects_out_of_range_port():
    with pytest.raises(ProbeRegistrationError):
        loopback_endpoint(70000)
    with pytest.raises(ProbeRegistrationError):
        loopback_endpoint(0)


# ---------------------------------------------------------------------------
# 有界执行器
# ---------------------------------------------------------------------------

def test_execute_sends_only_bounded_get_to_loopback_path():
    executor, transport, _ = _executor(
        TransportResponse(
            status_code=200,
            body=b'{"recovery_status":true}',
            headers={"Content-Type": "application/json"},
        )
    )
    result = executor.execute(_probe())
    assert result.error is None
    assert result.payload == {"recovery_status": True}
    assert result.status_code == 200

    request = transport.requests[0]
    assert request.method == "GET"
    assert request.host == "127.0.0.1"
    assert request.port == 18081
    assert request.path == "/health"
    assert request.follow_redirects is False
    assert request.use_proxy is False
    assert request.max_bytes == 4096
    assert request.timeout_ms == 1000
    assert request.url == "http://127.0.0.1:18081/health"


def test_non_2xx_response_writes_error_and_never_payload():
    executor, _, _ = _executor(
        TransportResponse(status_code=502, body=b'{"recovery_status":true}')
    )
    result = executor.execute(_probe())
    assert result.payload is None
    assert result.error is not None
    assert result.error["code"] == "HTTP_502"


@pytest.mark.parametrize("status", [400, 401, 404, 500, 503])
def test_4xx_5xx_statuses_are_error_codes(status: int):
    executor, _, _ = _executor(TransportResponse(status_code=status, body=b"{}"))
    result = executor.execute(_probe())
    assert result.payload is None
    assert result.error is not None
    assert result.error["code"] == f"HTTP_{status}"


def test_redirect_with_location_is_blocked():
    executor, _, _ = _executor(
        TransportResponse(
            status_code=302,
            body=b"",
            headers={"Location": "http://127.0.0.1:19999/admin"},
        )
    )
    result = executor.execute(_probe())
    assert result.payload is None
    assert result.error is not None
    assert result.error["code"] == "REDIRECT_BLOCKED"


def test_oversized_body_is_blocked_before_parsing():
    body = b'{"recovery_status":"' + b"a" * 5000 + b'"}'
    executor, _, _ = _executor(TransportResponse(status_code=200, body=body))
    result = executor.execute(_probe())
    assert result.payload is None
    assert result.error is not None
    assert result.error["code"] == "MALFORMED"
    assert result.truncated is True


@pytest.mark.parametrize("body", [b"not-json", b'[1,2,3]', b'"ok"', b""])
def test_non_json_object_is_rejected(body: bytes):
    executor, _, _ = _executor(TransportResponse(status_code=200, body=body))
    result = executor.execute(_probe())
    assert result.payload is None
    assert result.error is not None
    assert result.error["code"] == "MALFORMED"


def test_slow_drip_hits_absolute_timeout_even_if_status_is_200():
    executor, _, clock = _executor(
        TransportResponse(status_code=200, body=b'{"recovery_status":true}'),
        advance_ms=1500,
    )
    result = executor.execute(_probe())
    assert result.payload is None
    assert result.error is not None
    assert result.error["code"] == "TIMEOUT"
    assert result.elapsed_ms >= 1500
    # 单探针绝对时限不随读取次数重置。
    assert executor._timeout_ms == 1000  # noqa: SLF001 - 验证冻结常量


def test_timeout_is_trimmed_by_run_remaining_time():
    clock = FakeClock()
    executor, transport, _ = _executor(
        TransportResponse(status_code=200, body=b'{"ok":true}')
    )
    run_deadline = clock.current + timedelta(milliseconds=300)
    executor.execute(_probe(), run_deadline_at=run_deadline)
    request = transport.requests[0]
    assert request.timeout_ms == 300


def test_no_remaining_time_raises_deadline_error():
    clock = FakeClock()
    executor, _, _ = _executor(TransportResponse(status_code=200, body=b"{}"))
    with pytest.raises(ProbeDeadlineError):
        executor.execute(_probe(), run_deadline_at=clock.current)


def test_transport_timeout_and_os_error_are_normalized():
    def timeout_transport(request: ProbeRequest) -> TransportResponse:
        raise TimeoutError("socket timed out")

    def broken_transport(request: ProbeRequest) -> TransportResponse:
        raise OSError("connection refused")

    clock = FakeClock()
    timed = ProbeExecutor(transport=timeout_transport, clock=clock).execute(_probe())
    assert timed.error is not None and timed.error["code"] == "TIMEOUT"

    broken = ProbeExecutor(transport=broken_transport, clock=clock).execute(_probe())
    assert broken.error is not None and broken.error["code"] == "TRANSPORT_ERROR"


# ---------------------------------------------------------------------------
# 采集元数据写入
# ---------------------------------------------------------------------------

def test_builds_observation_with_explicit_scope_and_digest():
    case = _case()
    target = Target.from_dict(case["input"]["contract"]["target"])
    executor, _, _ = _executor(
        TransportResponse(
            status_code=200,
            body=b'{"recovery_status":true,"scope":"tenant:t2/workspace:w9"}',
        )
    )
    result = executor.execute(_probe())
    observation = result.to_observation(
        observation_id="obs-1",
        run_id="run-1",
        verification_round=1,
        scope="tenant:t1/workspace:w1",
        target=target,
        binding_revision="r17",
        observed_revision="r17",
        sequence=0,
    )
    # scope 由调用方显式给出，不得从 payload 反推。
    assert observation.scope == "tenant:t1/workspace:w1"
    assert observation.payload == result.payload
    assert observation.artifact_digest == payload_digest(result.payload)
    assert observation.source_group == "sg-a"
    assert observation.collector_id == "col-a"
    assert observation.elapsed_ms <= 1000


def test_error_observation_keeps_error_and_no_payload():
    case = _case()
    target = Target.from_dict(case["input"]["contract"]["target"])
    executor, _, _ = _executor(TransportResponse(status_code=503, body=b"{}"))
    result = executor.execute(_probe())
    observation = result.to_observation(
        observation_id="obs-err",
        run_id="run-1",
        verification_round=1,
        scope="tenant:t1/workspace:w1",
        target=target,
        binding_revision="r17",
        observed_revision=None,
        sequence=1,
    )
    assert observation.payload is None
    assert observation.error == {"code": "HTTP_503", "message": "HTTP 503"}
    assert observation.artifact_digest == payload_digest(observation.error)

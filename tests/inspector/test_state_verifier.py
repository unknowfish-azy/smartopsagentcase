"""C-R1 state verifier tests: actual state is derived from probes only."""

from agent.inspector.verifiers.state_verifier import (
    StateVerifier,
    collect_probes,
    http_probe,
    port_probe,
    process_probe,
    resolve_from_probes,
)

import http.server
import socket
import threading


class _ProbeHandler(http.server.BaseHTTPRequestHandler):
    seen_methods: list[str] = []

    def do_GET(self):  # noqa: N802
        self.__class__.seen_methods.append(self.command)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *_args):
        return


def _http_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _ProbeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_resolve_from_probes_covers_six_probe_shapes():
    cases = [
        ({"probe_type": "port", "status": "open"}, True),
        ({"probe_type": "http", "status_code": 200}, True),
        ({"probe_type": "process", "status": "running"}, True),
        ({"probe_type": "db", "timed_out": True}, False),
        ({"probe_type": "cluster", "status": "partial"}, False),
        ({"probe_type": "all_healthy", "healthy": True}, True),
    ]

    for probe, expected in cases:
        assert resolve_from_probes([probe]) is expected


def test_state_verifier_ignores_resolved_field_and_uses_probes():
    result = StateVerifier().verify(
        "任务已解决",
        {
            "resolved": True,
            "probes": [{"probe_type": "http", "status_code": 503}],
        },
    )

    assert result["false_success"] is True
    assert result["passed"] is False


def test_state_verifier_requires_probe_array():
    result = StateVerifier().verify(
        "任务已解决",
        {"resolved": False, "status": "502"},
    )

    assert result["checked"] is False
    assert "probes" in result["reason"]


def test_http_probe_performs_get_and_reports_status_code():
    _ProbeHandler.seen_methods.clear()
    server, thread = _http_server()
    try:
        probe = http_probe(f"http://127.0.0.1:{server.server_port}/health")
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert probe["probe_type"] == "http"
    assert probe["status_code"] == 200
    assert probe["status"] == "ok"
    assert _ProbeHandler.seen_methods == ["GET"]


def test_port_probe_reports_open_and_closed_ports():
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    try:
        assert port_probe("127.0.0.1", port)["status"] == "open"
    finally:
        listener.close()

    closed = port_probe("127.0.0.1", port)
    assert closed["probe_type"] == "port"
    assert closed["status"] in {"closed", "refused", "error", "timeout"}


def test_process_probe_finds_current_python_process():
    probe = process_probe("python")

    assert probe["probe_type"] == "process"
    assert probe["status"] == "running"
    assert probe["match_count"] >= 1


def test_collect_probes_accepts_grouped_targets_without_resolved_field():
    probes = collect_probes({"process": ["python"]})

    assert probes and probes[0]["probe_type"] == "process"
    assert all("resolved" not in probe for probe in probes)


def test_unknown_probe_is_unverifiable_and_not_false_success():
    result = StateVerifier().verify("服务已恢复", {"probes": [{"type": "http", "status_code": 0}]})
    assert result["checked"] is False
    assert result["passed"] is None
    assert result.get("false_success") is not True


def test_http_probe_checks_observed_configuration_version():
    assert resolve_from_probes([{"type": "http", "status_code": 200,
                                 "expected_version": "v2", "observed_version": "v1"}]) is False


def test_negated_success_claim_is_not_a_success_claim():
    result = StateVerifier().verify("服务尚未恢复", {"probes": [{"type": "port", "open": False}]})
    assert result.get("false_success") is not True


def test_non_mapping_probe_is_unverifiable():
    result = StateVerifier().verify("服务已恢复", {"probes": [None]})
    assert result["checked"] is False


def test_http_502_probe_reaches_pipeline_as_rejected():
    from agent.inspector.pipeline import InspectorPipeline

    class BrokenHandler(_ProbeHandler):
        def do_GET(self):
            self.send_response(502)
            self.end_headers()

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), BrokenHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        probe = http_probe(f"http://127.0.0.1:{server.server_port}/health")
        result = InspectorPipeline().run({"agent_claim": "服务已恢复", "actual_state": {"probes": [probe]}})
        assert probe["status_code"] == 502
        assert result.to_dict()["status"] == "REJECTED"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


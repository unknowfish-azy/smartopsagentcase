"""PROBE-P1-01：自持有 loopback 服务的端到端驱动测试。

与 test_probes.py 的注入式假 transport 不同，本文件在 127.0.0.1 临时端口
启动真实 HTTP 服务，走 collector.loopback_transport 的真实 socket：
连接 + 完整读取 + 解析共享同一个 1 秒绝对时限。

覆盖验收证据：健康窗口 VERIFIED、HTTP 200 但业务 false CONTRADICTED、
502 INSUFFICIENT、慢速滴流 TIMEOUT、超大 body MALFORMED、重定向拒绝、
重试计费、重启继承持久化预算。
"""

from __future__ import annotations

import contextlib
import http.server
import json
import threading
import time
from pathlib import Path

import pytest

from agent.recovery_contracts import (
    Claim,
    LoopbackProbeClient,
    Probe,
    ProbeRegistry,
    RecoveryContract,
    RunBudget,
    add_ms,
    choose_next,
    evaluate,
    format_time,
    loopback_endpoint,
    parse_time,
    utc_now,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCOPE = "tenant:t1/workspace:w1"
REVISION = "r17"
RUN_ID = "run-probe-p1-01"


def _case() -> dict:
    return json.loads((FIXTURES / "vp01-positive.json").read_text(encoding="utf-8"))


def _contract() -> RecoveryContract:
    return RecoveryContract.from_dict(_case()["input"]["contract"])


def _claim() -> Claim:
    return Claim.from_dict(_case()["input"]["claim"])


class _ModeHandler(http.server.BaseHTTPRequestHandler):
    """按 server.mode 提供冻结路径上的固定响应；只实现 GET。"""

    def log_message(self, *args) -> None:  # 静默测试日志
        return

    def _send_json(self, status: int, body: dict) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 约定
        if self.path not in ("/health", "/ready", "/api/health"):
            self._send_json(404, {"error": "unknown path"})
            return
        mode = getattr(self.server, "probe_mode", "healthy")
        if mode == "healthy":
            self._send_json(200, {"recovery_status": True, "observed_revision": REVISION})
        elif mode == "business_false":
            # HTTP 200 但业务字段为 false：恢复契约的关键反例。
            self._send_json(200, {"recovery_status": False, "observed_revision": REVISION})
        elif mode == "http_error":
            self._send_json(502, {"error": "bad gateway"})
        elif mode == "redirect":
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{self.server.server_address[1]}/admin")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif mode == "big":
            self._send_json(200, {"recovery_status": True, "pad": "a" * 5000})
        elif mode == "slow":
            # 慢速滴流：分段写 body，每段都在单次 socket 超时之内，
            # 但累计超过 1 秒绝对时限。
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "32")
            self.end_headers()
            try:
                for chunk in (b'{"recovery_status":', b" true", b',"pad":"xx"}'):
                    self.wfile.write(chunk)
                    self.wfile.flush()
                    time.sleep(0.7)
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:  # pragma: no cover - 未登记模式
            self._send_json(500, {"error": f"unknown mode {mode}"})


@contextlib.contextmanager
def _loopback_server(mode: str):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _ModeHandler)
    server.probe_mode = mode
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _probe(probe_id: str, port: int, *, collector_id: str, source_group: str) -> Probe:
    return Probe(
        probe_id=probe_id,
        collector_id=collector_id,
        collector_version="1.0.0",
        obligation_ids=("obl-business-health",),
        cost=1,
        permission="probe:read",
        read_only=True,
        endpoint=loopback_endpoint(port),
        path="/health",
        target_id="service:edge-nginx",
        source_group=source_group,
    )


def _results(contract, claim, observations):
    return evaluate(
        contract,
        claim,
        observations,
        utc_now(),
        run_id=RUN_ID,
        verification_round=1,
        authorized_scopes={SCOPE},
    ).obligation_results


def _execute(client, registry, budget, decision, observations, sequence) -> None:
    result = client.execute(decision["selected_probe_id"], run_deadline_at=budget.deadline_at)
    budget.record_call()  # 每次真实调用都记账；重试同样扣费。
    payload = result.payload or {}
    observation = result.to_observation(
        observation_id=f"obs-{sequence}-{decision['selected_probe_id']}",
        run_id=budget.run_id,
        verification_round=budget.verification_round,
        scope=SCOPE,
        target=_contract().target,
        binding_revision=REVISION,
        observed_revision=payload.get("observed_revision"),
        sequence=sequence,
    )
    observations.append(observation)


# ---------------------------------------------------------------------------
# 端到端：真实 loopback 采样窗口
# ---------------------------------------------------------------------------

def test_real_loopback_three_group_window_verified():
    contract = _contract()
    claim = _claim()
    with _loopback_server("healthy") as port_a, _loopback_server("healthy") as port_b:
        registry = ProbeRegistry()
        registry.register(_probe("probe-a", port_a, collector_id="col-a", source_group="sg-a"))
        registry.register(_probe("probe-b", port_b, collector_id="col-b", source_group="sg-b"))
        client = LoopbackProbeClient(registry)
        budget = RunBudget.from_contract(contract, run_id=RUN_ID, started_at=utc_now())

        observations = []
        sequence = 0
        next_slot_at = None
        wait_seen = None
        for group in range(3):
            if group > 0:
                # 采样槽未到：调度必须输出 WAIT，且不扣调用次数。
                wait_decision = choose_next(
                    contract, _results(contract, claim, observations), registry, budget,
                    utc_now(), permissions={"probe:read"}, next_slot_at=next_slot_at,
                )
                assert wait_decision["decision"] == "WAIT"
                assert wait_decision["budget_after"] == wait_decision["budget_before"]
                wait_seen = wait_decision
                delay = (parse_time(next_slot_at) - utc_now()).total_seconds()
                if delay > 0:
                    time.sleep(delay)
            executed: set[str] = set()
            for _ in range(2):  # 每组 A/B 两条来源
                decision = choose_next(
                    contract, _results(contract, claim, observations), registry, budget,
                    utc_now(), permissions={"probe:read"}, executed_probe_ids=executed,
                )
                assert decision["decision"] == "SELECTED"
                _execute(client, registry, budget, decision, observations, sequence)
                executed.add(decision["selected_probe_id"])
                sequence += 1
            group_time = max(item.observed_at for item in observations[-2:])
            # 下一组最早启动 = 前组组时间 + 2200ms（>2000 留时钟粒度余量）。
            next_slot_at = format_time(add_ms(parse_time(group_time), 2200))

        final = evaluate(
            contract, claim, observations, utc_now(),
            run_id=RUN_ID, verification_round=1, authorized_scopes={SCOPE},
        )
        assert final.verdict == "VERIFIED"
        assert final.window.satisfied is True
        assert final.window.valid_groups == 3
        assert budget.calls_used == 6
        assert wait_seen is not None
        assert len(final.used_observations) == 6


def test_real_loopback_http200_business_false_is_contradicted():
    contract = _contract()
    claim = _claim()
    with _loopback_server("business_false") as port:
        registry = ProbeRegistry()
        registry.register(_probe("probe-a", port, collector_id="col-a", source_group="sg-a"))
        client = LoopbackProbeClient(registry)
        budget = RunBudget.from_contract(contract, run_id=RUN_ID, started_at=utc_now())
        result = client.execute("probe-a", run_deadline_at=budget.deadline_at)
        budget.record_call()
        assert result.status_code == 200
        observation = result.to_observation(
            observation_id="obs-false-1", run_id=RUN_ID, verification_round=1,
            scope=SCOPE, target=contract.target, binding_revision=REVISION,
            observed_revision=result.payload.get("observed_revision"),
        )
        evaluation = evaluate(
            contract, claim, [observation], utc_now(),
            run_id=RUN_ID, verification_round=1, authorized_scopes={SCOPE},
        )
        assert evaluation.verdict == "CONTRADICTED"
        assert evaluation.obligation_results[0].value == "FALSE"


def test_real_loopback_502_is_insufficient_not_success():
    contract = _contract()
    claim = _claim()
    with _loopback_server("http_error") as port:
        registry = ProbeRegistry()
        registry.register(_probe("probe-a", port, collector_id="col-a", source_group="sg-a"))
        client = LoopbackProbeClient(registry)
        result = client.execute("probe-a")
        assert result.payload is None
        assert result.error == {"code": "HTTP_502", "message": "HTTP 502"}
        observation = result.to_observation(
            observation_id="obs-502-1", run_id=RUN_ID, verification_round=1,
            scope=SCOPE, target=contract.target, binding_revision=REVISION,
            observed_revision=None,
        )
        evaluation = evaluate(
            contract, claim, [observation], utc_now(),
            run_id=RUN_ID, verification_round=1, authorized_scopes={SCOPE},
        )
        assert evaluation.verdict == "INSUFFICIENT"
        assert evaluation.obligation_results[0].value == "UNKNOWN"
        assert "MALFORMED" in evaluation.obligation_results[0].reason_codes


# ---------------------------------------------------------------------------
# 真实 socket 边界：slow-drip / 超大 body / 重定向
# ---------------------------------------------------------------------------

def test_real_socket_slow_drip_hits_absolute_deadline():
    with _loopback_server("slow") as port:
        registry = ProbeRegistry()
        registry.register(_probe("probe-a", port, collector_id="col-a", source_group="sg-a"))
        client = LoopbackProbeClient(registry)
        started = time.monotonic()
        result = client.execute("probe-a")
        wall_ms = (time.monotonic() - started) * 1000
        assert result.error is not None
        assert result.error["code"] == "TIMEOUT"
        # 绝对时限到期即停止：不会等服务端 2.1 秒滴流完成。
        assert 1000 <= result.elapsed_ms
        assert wall_ms < 1900


def test_real_socket_oversized_body_is_rejected():
    with _loopback_server("big") as port:
        registry = ProbeRegistry()
        registry.register(_probe("probe-a", port, collector_id="col-a", source_group="sg-a"))
        client = LoopbackProbeClient(registry)
        result = client.execute("probe-a")
        assert result.payload is None
        assert result.error is not None
        assert result.error["code"] == "MALFORMED"
        assert result.truncated is True
        assert result.bytes_read <= 4097


def test_real_socket_redirect_is_not_followed():
    with _loopback_server("redirect") as port:
        registry = ProbeRegistry()
        registry.register(_probe("probe-a", port, collector_id="col-a", source_group="sg-a"))
        client = LoopbackProbeClient(registry)
        result = client.execute("probe-a")
        assert result.payload is None
        assert result.error is not None
        assert result.error["code"] == "REDIRECT_BLOCKED"
        assert result.status_code == 302


# ---------------------------------------------------------------------------
# 计费与重启
# ---------------------------------------------------------------------------

def test_retry_after_failure_charges_budget_again():
    contract = _contract()
    with _loopback_server("http_error") as port:
        registry = ProbeRegistry()
        registry.register(_probe("probe-a", port, collector_id="col-a", source_group="sg-a"))
        client = LoopbackProbeClient(registry)
        budget = RunBudget.from_contract(contract, run_id=RUN_ID, started_at=utc_now())
        for _ in range(2):  # 同一探针失败重试：每次都计费
            result = client.execute("probe-a", run_deadline_at=budget.deadline_at)
            assert result.error is not None
            budget.record_call()
        assert budget.calls_used == 2
        decision = choose_next(
            contract, _results(contract, _claim(), []), registry, budget,
            utc_now(), permissions={"probe:read"},
        )
        assert decision["decision"] == "SELECTED"
        assert decision["budget_before"]["calls_used"] == 2
        assert decision["budget_after"]["calls_used"] == 3


def test_restart_inherits_persisted_budget_and_deadline():
    contract = _contract()
    budget = RunBudget.from_contract(
        contract, run_id=RUN_ID, started_at=utc_now(), calls_used=6, verification_round=2
    )
    # 持久化的是 ISO wall-clock deadline 与账本；进程重启只恢复这些字段，
    # 绝不比较旧进程的单调时钟。
    persisted = {
        "run_id": budget.run_id,
        "max_probe_calls": budget.max_probe_calls,
        "deadline_at": format_time(budget.deadline_at),
        "calls_used": budget.calls_used,
        "verification_round": budget.verification_round,
    }
    restored = RunBudget(**persisted)
    assert restored.calls_used == 6
    assert restored.calls_remaining == 6
    assert restored.verification_round == 2
    assert format_time(restored.deadline_at) == persisted["deadline_at"]

    registry = ProbeRegistry()
    with _loopback_server("healthy") as port:
        registry.register(_probe("probe-a", port, collector_id="col-a", source_group="sg-a"))
        decision = choose_next(
            contract, _results(contract, _claim(), []), registry, restored,
            utc_now(), permissions={"probe:read"},
        )
        assert decision["decision"] == "SELECTED"
        assert decision["budget_before"]["calls_used"] == 6

        # deadline 已过（如重启耗时超预期）：恢复出的 run 必须 STOP。
        late = format_time(parse_time(persisted["deadline_at"]))
        decision = choose_next(
            contract, _results(contract, _claim(), []), registry, restored,
            late, permissions={"probe:read"},
        )
        assert decision["decision"] == "STOP"
        assert decision["stop_reason"] == "DEADLINE_EXCEEDED"

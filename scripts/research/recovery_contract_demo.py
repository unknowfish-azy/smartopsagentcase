"""HC-11 loopback 机制 PoC 演示：证据义务 -> 补证 -> 契约 -> 同证据回放。

边界（有意如此，不是遗漏）：
- 只消费 ``agent.recovery_contracts`` 已验收的 N02—N05 实现，不改任何模块与测试；
- 只启动绑定 ``127.0.0.1`` 的本地 HTTP stub（随机端口，``http.server``），
  结束后关闭；不启动 uvicorn/Java/前端服务；
- 不访问外网、不调用 LLM、不使用随机数（端口由操作系统分配，不参与判定）；
- 探针约束由 ``probes.py``/``collector.py`` 强制：4KiB 响应上限、1s 绝对超时、
  禁代理、禁重定向；本脚本只做断言与记录。

四个场景：
A 全部健康 -> 义务 TRUE -> 窗口满足 -> VERIFIED 并签发 ACTIVE 回执；
B HTTP 200 但业务 ``healthy=false`` -> CONTRADICTED（不得因 200 判恢复）；
C 某来源 502 -> ``error=HTTP_502`` -> INSUFFICIENT（不是 FALSE/TRUE）；
D 用 A 的证据包 replay，携带 ``expected_revision`` r17->r16 变形 -> 判定翻转
  并给出差异码，且回放全程不补探（stub 请求计数不变）。

运行：``python scripts/research/recovery_contract_demo.py``
产物：``.runtime/hc-11/run.json``、``.runtime/hc-11/summary.md``
"""

from __future__ import annotations

import copy
import json
import platform
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    # 让 `python scripts/research/recovery_contract_demo.py` 能导入项目包。
    sys.path.insert(0, str(ROOT))

from agent.recovery_contracts import (
    ABSOLUTE_TIMEOUT_MS,
    ALLOWED_PATHS,
    MAX_RESPONSE_BYTES,
    POLICY_VERSION,
    PROBE_HOST,
    Claim,
    LoopbackProbeClient,
    Probe,
    ProbeRegistry,
    RecoveryContract,
    RunBudget,
    canonical_json,
    choose_next,
    evaluate,
    format_time,
    loopback_endpoint,
    minimum_calls_for_round,
    object_digest,
    parse_time,
    replay,
    utc_now,
    verify,
)
from agent.recovery_contracts.replay import COMPLETE as REPLAY_COMPLETE

RUNTIME_DIR = ROOT / ".runtime" / "hc-11"
RUN_JSON = RUNTIME_DIR / "run.json"
SUMMARY_MD = RUNTIME_DIR / "summary.md"

SAMPLE_SLOTS = 3
SLOT_GAP_MS = 2400  # 下一组最早启动 = 前组组时间 + 2400ms（> 冻结的 2000ms 下界）
REPLAY_REPEATS = 100
SCOPE = "tenant:t1/workspace:w1"
TARGET_ID = "service:hc11-demo"
REVISION = "r17"
VARIANT_REVISION = "r16"
OBLIGATION_ID = "obl_business_health"

# (probe_suffix, path, source_group)；三个来源组，每个来源组在三个采样组各观测一次。
PROBE_SPECS = (
    ("a", "/health", "sg_a"),
    ("b", "/ready", "sg_b"),
    ("c", "/api/health", "sg_c"),
)


# ---------------------------------------------------------------------------
# 本地 stub：仅 127.0.0.1，按路径返回受控响应
# ---------------------------------------------------------------------------

@dataclass
class StubState:
    """stub 的当前场景与请求计数；回放前后对比计数即可证明“不补探”。"""

    name: str = "A"
    counts: dict[str, int] = field(default_factory=dict)
    total: int = 0

    def switch(self, name: str) -> None:
        self.name = name

    def record(self, path: str) -> None:
        self.counts[path] = self.counts.get(path, 0) + 1
        self.total += 1

    def snapshot(self) -> dict[str, Any]:
        return {"total": self.total, "by_path": dict(self.counts)}


class StubHandler(BaseHTTPRequestHandler):
    server_version = "HC11LoopbackStub/1.0"
    protocol_version = "HTTP/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:  # 不向 stderr 打印访问日志
        return

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 约定
        state: StubState = self.server.state  # type: ignore[attr-defined]
        state.record(self.path)
        if self.path not in ALLOWED_PATHS:
            self._send(404, {"error": "not_found"})
            return
        if state.name == "C" and self.path == "/ready":
            # 场景 C：某来源返回 502，探针必须记 error=HTTP_502，不得塞 payload。
            self._send(502, {"error": "upstream_unavailable"})
            return
        healthy = True
        if state.name == "B" and self.path == "/health":
            # 场景 B：HTTP 200 但业务自检失败。
            healthy = False
        body = {
            "healthy": healthy,
            "revision": REVISION,
            "payment_ready": healthy,
            "request_id": f"stub-{self.path.strip('/').replace('/', '-')}-{state.total}",
        }
        self._send(200, body)

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class StubServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, state: StubState) -> None:
        super().__init__((PROBE_HOST, 0), StubHandler)
        self.state = state


# ---------------------------------------------------------------------------
# 契约 / 声明 / 探针登记
# ---------------------------------------------------------------------------

def _resign(mapping: dict[str, Any]) -> dict[str, Any]:
    """重算对象 digest（仅删除自身 digest 字段后做 canonical 摘要）。"""
    mapping["digest"] = object_digest(
        {key: value for key, value in mapping.items() if key != "digest"}
    )
    return mapping


def _build_contract_raw(port: int) -> dict[str, Any]:
    target = {
        "target_id": TARGET_ID,
        "target_kind": "SERVICE",
        "endpoint": f"http://{PROBE_HOST}:{port}/health",
    }
    raw: dict[str, Any] = {
        "schema_version": "recovery-contract/v1",
        "id": "rc_hc11_demo",
        "version": "1",
        "scope": SCOPE,
        "target": target,
        "expected_revision": REVISION,
        "template_id": "template:hc11-demo",
        "template_version": "1",
        "obligations": [
            {
                "obligation_id": OBLIGATION_ID,
                "predicate_id": "business_health_flag",
                "predicate_version": "1",
                "required": True,
                "weight": 1,
                "collector_ids": ["col_a", "col_b", "col_c"],
                "source_groups": ["sg_a", "sg_b", "sg_c"],
                "binding_revision": REVISION,
                "scope": SCOPE,
                "target": target,
                "predicate_params": {"field": "healthy", "expected": True},
            }
        ],
        "source_groups": ["sg_a", "sg_b", "sg_c"],
        "window": {
            "sample_groups": 3,
            "min_first_last_gap_ms": 4000,
            "max_adjacent_gap_ms": 4000,
            "max_intra_group_skew_ms": 1250,
            "min_next_group_gap_ms": 2000,
        },
        "budgets": {
            "max_probe_calls": 12,
            "per_probe_timeout_ms": 1000,
            "run_deadline_ms": 30000,
            "evidence_ttl_ms": 15000,
            "receipt_ttl_ms": 8000,
        },
        "expires_after": 3600000,
    }
    return _resign(raw)


def _build_claim_raw(contract_raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "claim_hc11_demo",
        "contract_digest": contract_raw["digest"],
        "scope": SCOPE,
        "target": copy.deepcopy(contract_raw["target"]),
        "expected_revision": REVISION,
        "claim_type": "BUSINESS_RECOVERY",
    }


def _build_registry(port: int) -> ProbeRegistry:
    endpoint = loopback_endpoint(port)
    registry = ProbeRegistry()
    for suffix, path, group in PROBE_SPECS:
        registry.register(
            Probe(
                probe_id=f"probe_{suffix}",
                collector_id=f"col_{suffix}",
                collector_version="1.0.0",
                obligation_ids=(OBLIGATION_ID,),
                cost=1,
                permission="read_only_probe",
                read_only=True,
                endpoint=endpoint,
                path=path,
                target_id=TARGET_ID,
                source_group=group,
            )
        )
    return registry


def _probe_summary(registry: ProbeRegistry) -> list[dict[str, Any]]:
    return [
        {
            "probe_id": probe.probe_id,
            "collector_id": probe.collector_id,
            "source_group": probe.source_group,
            "path": probe.path,
            "endpoint": probe.endpoint,
            "cost": probe.cost,
            "read_only": probe.read_only,
        }
        for probe in registry.probes()
    ]


# ---------------------------------------------------------------------------
# 采集（真实 loopback GET）与补证调度
# ---------------------------------------------------------------------------

def _sleep_until(iso_time: str) -> None:
    """按调度给出的 next_eligible_at 等待；只读录制/判定时间，不额外加抖动。"""
    target = parse_time(iso_time)
    delay = (target - utc_now()).total_seconds()
    if delay > 0:
        time.sleep(delay + 0.03)


def _decision_brief(decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision_id": decision["decision_id"],
        "decision": decision["decision"],
        "selected_probe_id": decision["selected_probe_id"],
        "next_eligible_at": decision["next_eligible_at"],
        "stop_reason": decision["stop_reason"],
        "score": decision["score"],
        "calls_used": decision["budget_after"]["calls_used"],
        "extensions": copy.deepcopy(decision.get("extensions", {})),
    }


def _call_record(result: Any) -> dict[str, Any]:
    return {
        "probe_id": result.probe_id,
        "source_group": result.source_group,
        "path": result.path,
        "status_code": result.status_code,
        "payload": copy.deepcopy(result.payload),
        "error": copy.deepcopy(result.error),
        "bytes_read": result.bytes_read,
        "elapsed_ms": result.elapsed_ms,
        "observed_at": format_time(result.observed_at),
    }


def _observation_from_result(
    result: Any,
    *,
    scenario: str,
    slot: int,
    sequence: int,
    run_id: str,
    contract: RecoveryContract,
) -> Any:
    payload = result.payload if isinstance(result.payload, dict) else None
    observed_revision = payload.get("revision") if payload else None
    observation_id = f"obs_{scenario.lower()}_{result.probe_id}_{slot}"
    return result.to_observation(
        observation_id=observation_id,
        run_id=run_id,
        verification_round=1,
        scope=contract.scope,
        target=contract.target,
        binding_revision=contract.expected_revision,
        observed_revision=observed_revision,
        sequence=sequence,
    )


def run_scenario(
    name: str,
    *,
    contract: RecoveryContract,
    claim: Claim,
    registry: ProbeRegistry,
    client: LoopbackProbeClient,
    state: StubState,
    started_at: datetime,
) -> dict[str, Any]:
    """用 choose_next 驱动补证：状态槽未到时 WAIT，到时 SELECTED，反例 STOP。"""
    state.switch(name)
    stub_before = state.snapshot()
    run_id = f"run_hc11_{name.lower()}"
    budget = RunBudget.from_contract(contract, run_id=run_id, started_at=started_at)
    observations: list[Any] = []
    calls: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    slot_times: list[datetime] = []
    stop_reason: str | None = None

    for slot in range(SAMPLE_SLOTS):
        executed: set[str] = set()
        slot_start_index = len(observations)
        planned_next_at = (
            None if slot == 0 else slot_times[-1] + timedelta(milliseconds=SLOT_GAP_MS)
        )
        while True:
            now = utc_now()
            evaluation = evaluate(
                contract, claim, observations, now, run_id=run_id, verification_round=1
            )
            decision = choose_next(
                contract,
                evaluation.obligation_results,
                registry,
                budget,
                now,
                executed_probe_ids=executed,
                next_slot_at=planned_next_at,
                required_calls_ahead=minimum_calls_for_round(
                    contract, SAMPLE_SLOTS - slot
                ),
            )
            decisions.append(_decision_brief(decision))
            if decision["decision"] == "WAIT":
                _sleep_until(decision["next_eligible_at"])
                continue
            if decision["decision"] == "STOP":
                # 有效业务反例令本轮终止；补证不能抵消反例。
                stop_reason = decision["stop_reason"]
                break
            probe_id = decision["selected_probe_id"]
            budget.record_call()
            result = client.execute(probe_id, run_deadline_at=budget.deadline_at)
            observations.append(
                _observation_from_result(
                    result,
                    scenario=name,
                    slot=slot,
                    sequence=len(observations),
                    run_id=run_id,
                    contract=contract,
                )
            )
            calls.append(_call_record(result))
            executed.add(probe_id)
            if len(executed) >= len(registry.probes()):
                break
        if stop_reason is not None:
            break
        slot_times.append(max(item.observed_at for item in observations[slot_start_index:]))

    decision_time = utc_now()
    evaluation = evaluate(
        contract, claim, observations, decision_time, run_id=run_id, verification_round=1
    )
    receipt = verify(
        contract,
        claim,
        observations,
        decision_time,
        run_id=run_id,
        verification_round=1,
        authorized_scopes=[contract.scope],
        receipt_id=f"rcpt_hc11_{name.lower()}",
    )
    stub_after = state.snapshot()

    return {
        "scenario": f"{name}",
        "run_id": run_id,
        "decision_time": format_time(decision_time),
        "verdict": receipt.verdict,
        "receipt_id": receipt.id,
        "receipt_state": receipt.receipt_state,
        "receipt_digest": receipt.snapshot_digest(),
        "receipt_obj": receipt,
        "window": evaluation.window.to_dict(),
        "obligation_results": [item.to_dict() for item in evaluation.obligation_results],
        "observations": [item.to_dict() for item in observations],
        "observations_obj": observations,
        "calls": calls,
        "scheduler_decisions": decisions,
        "stop_reason": stop_reason,
        "calls_used": budget.calls_used,
        "stub_requests": {
            "before": stub_before,
            "after": stub_after,
            "delta_total": stub_after["total"] - stub_before["total"],
        },
    }


# ---------------------------------------------------------------------------
# 录制包（ReplayBundle）与回放
# ---------------------------------------------------------------------------

def _build_bundle(
    scenario: dict[str, Any],
    contract_raw: dict[str, Any],
    claim_raw: dict[str, Any],
) -> dict[str, Any]:
    observations = scenario["observations"]
    probe_map: dict[str, list[str]] = {}
    source_mapping: dict[str, str] = {}
    order: list[str] = []
    for observation in observations:
        probe_map.setdefault(observation["probe_id"], []).append(observation["id"])
        source_mapping[observation["collector_id"]] = observation["source_group"]
        order.append(observation["id"])
    started_at = parse_time(observations[0]["observed_at"])
    bundle: dict[str, Any] = {
        "schema_version": "recovery-replay/v1",
        "bundle_id": "bundle_hc11_a",
        "contract": copy.deepcopy(contract_raw),
        "claim": copy.deepcopy(claim_raw),
        "observations": copy.deepcopy(observations),
        "source_mapping": source_mapping,
        "policy_version": POLICY_VERSION,
        "policy_config": {"selection": "weighted_coverage", "window": "v1"},
        "decision_clock": {
            "mode": "RECORDED",
            "decision_time": scenario["decision_time"],
            "monotonic_origin_id": "mono_hc11_a",
        },
        "observation_order": order,
        "prerecorded_probe_map": probe_map,
        "budget": {
            "limits": copy.deepcopy(contract_raw["budgets"]),
            "calls_used": scenario["calls_used"],
            "deadline_at": format_time(started_at + timedelta(milliseconds=30000)),
        },
        "run_event_refs": [scenario["run_id"]],
        "dependency_versions": {
            "python": platform.python_version(),
            "evaluator": POLICY_VERSION,
        },
        "digest": "sha256:" + "0" * 64,
        "parent_bundle_id": None,
        "mutation_diff": None,
        "is_historical_fact": True,
    }
    return _resign(bundle)


def _build_revision_variant(
    bundle: dict[str, Any], contract_raw: dict[str, Any], claim_raw: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """同一份录制证据，只把契约/声明的 expected_revision 改为 r16（显式变形）。"""
    variant_contract = copy.deepcopy(contract_raw)
    variant_contract["expected_revision"] = VARIANT_REVISION
    for obligation in variant_contract["obligations"]:
        obligation["binding_revision"] = VARIANT_REVISION
    variant_contract = _resign(variant_contract)

    variant_claim = copy.deepcopy(claim_raw)
    variant_claim["contract_digest"] = variant_contract["digest"]
    variant_claim["expected_revision"] = VARIANT_REVISION

    variant_bundle = copy.deepcopy(bundle)
    variant_bundle["bundle_id"] = "bundle_hc11_a_r16"
    variant_bundle["contract"] = copy.deepcopy(variant_contract)
    variant_bundle["claim"] = copy.deepcopy(variant_claim)
    variant_bundle["parent_bundle_id"] = bundle["bundle_id"]
    variant_bundle["mutation_diff"] = {
        "kind": "EXPECTED_REVISION_CHANGED",
        "field": "expected_revision",
        "from": REVISION,
        "to": VARIANT_REVISION,
    }
    variant_bundle["is_historical_fact"] = False
    variant_bundle = _resign(variant_bundle)
    return variant_bundle, variant_contract, variant_claim


def _replay_summary(result: Any) -> dict[str, Any]:
    payload = result.to_dict()
    return {
        "bundle_id": payload["bundle_id"],
        "replay_state": payload["replay_state"],
        "verdict": payload["verdict"],
        "recorded_verdict": payload["recorded_verdict"],
        "original_receipt_digest": payload["original_receipt_digest"],
        "recomputed_receipt_digest": payload["recomputed_receipt_digest"],
        "reason_codes": payload["reason_codes"],
        "diff_reason_codes": payload["diff_reason_codes"],
        "obligation_diffs": payload["obligation_diffs"],
    }


def build_replay_evidence(
    base_scenario: dict[str, Any],
    contract: RecoveryContract,
    claim: Claim,
    contract_raw: dict[str, Any],
    claim_raw: dict[str, Any],
    state: StubState,
) -> dict[str, Any]:
    """D：用 A 的证据包回放；正常回放 + r16 变形回放 + 100 次确定性重复。"""
    bundle = _build_bundle(base_scenario, contract_raw, claim_raw)
    receipt = base_scenario["receipt_obj"]
    required_probes = {
        f"probe_{suffix}": [OBLIGATION_ID] for suffix, _path, _group in PROBE_SPECS
    }

    stub_before_replay = state.snapshot()

    base_result = replay(
        bundle, contract, claim, authorized_scopes=[contract.scope],
        recorded_receipt=receipt, required_probes=required_probes,
    )

    # 100 次重复：verdict、逐义务结果、整包摘要必须完全一致。
    distinct_outputs: set[str] = set()
    distinct_verdicts: set[str] = set()
    distinct_obligations: set[str] = set()
    for _ in range(REPLAY_REPEATS):
        repeated = replay(
            bundle, contract, claim, authorized_scopes=[contract.scope],
            recorded_receipt=receipt, required_probes=required_probes,
        )
        distinct_outputs.add(canonical_json(repeated.to_dict()))
        distinct_verdicts.add(str(repeated.verdict))
        distinct_obligations.add(
            canonical_json([item.to_dict() for item in repeated.obligation_results])
        )

    variant_bundle, variant_contract_raw, variant_claim_raw = _build_revision_variant(
        bundle, contract_raw, claim_raw
    )
    variant_result = replay(
        variant_bundle,
        RecoveryContract.from_dict(variant_contract_raw),
        Claim.from_dict(variant_claim_raw),
        authorized_scopes=[contract.scope],
        recorded_receipt=receipt,
        required_probes=required_probes,
    )

    stub_after_replay = state.snapshot()

    return {
        "bundle": bundle,
        "bundle_id": bundle["bundle_id"],
        "bundle_digest": bundle["digest"],
        "recorded_receipt_id": receipt.id,
        "recorded_receipt_digest": receipt.snapshot_digest(),
        "base_replay": _replay_summary(base_result),
        "determinism": {
            "repeat_runs": REPLAY_REPEATS,
            "distinct_outputs": len(distinct_outputs),
            "distinct_verdicts": sorted(distinct_verdicts),
            "distinct_obligation_result_sets": len(distinct_obligations),
            "consistent": len(distinct_outputs) == 1,
        },
        "variant": {
            **_replay_summary(variant_result),
            "mutation_diff": variant_bundle["mutation_diff"],
            "parent_bundle_id": variant_bundle["parent_bundle_id"],
            "is_historical_fact": variant_bundle["is_historical_fact"],
            "variant_bundle_digest": variant_bundle["digest"],
        },
        "no_new_probe": {
            "stub_requests_before": stub_before_replay,
            "stub_requests_after": stub_after_replay,
            "delta_total": stub_after_replay["total"] - stub_before_replay["total"],
            "proved": stub_after_replay["total"] == stub_before_replay["total"],
        },
    }


# ---------------------------------------------------------------------------
# 证据写出
# ---------------------------------------------------------------------------

def _scenario_evidence(scenario: dict[str, Any], expected: str) -> dict[str, Any]:
    return {
        "scenario": scenario["scenario"],
        "description": scenario.get("description", ""),
        "run_id": scenario["run_id"],
        "expected_verdict": expected,
        "verdict": scenario["verdict"],
        "matched": scenario["verdict"] == expected,
        "receipt_id": scenario["receipt_id"],
        "receipt_state": scenario["receipt_state"],
        "receipt_digest": scenario["receipt_digest"],
        "decision_time": scenario["decision_time"],
        "calls_used": scenario["calls_used"],
        "stop_reason": scenario["stop_reason"],
        "window": scenario["window"],
        "obligation_results": scenario["obligation_results"],
        "scheduler_decisions": scenario["scheduler_decisions"],
        "calls": scenario["calls"],
        "observations": scenario["observations"],
        "stub_requests": scenario["stub_requests"],
    }


def write_evidence(payload: dict[str, Any], summary: str) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    RUN_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    SUMMARY_MD.write_text(summary, encoding="utf-8", newline="\n")


def _render_summary(payload: dict[str, Any]) -> str:
    scenarios = payload["scenarios"]
    replay_ev = payload["replay"]
    rows = "\n".join(
        f"| {item['scenario']} | {item['expected_verdict']} | {item['verdict']} | "
        f"{'是' if item['matched'] else '否'} | {item['receipt_id']} | "
        f"{item['receipt_state']} | {item['calls_used']} |"
        for item in scenarios
    )
    variant = replay_ev["variant"]
    return f"""# HC-11 loopback 机制 PoC 运行摘要

- 命令：`python scripts/research/recovery_contract_demo.py`
- 运行时间：{payload['started_at']} ~ {payload['finished_at']}（时区 {payload['timezone']}）
- 契约：`{payload['contract']['id']}` / digest `{payload['contract']['digest']}`
- 目标 revision：契约期望 `{payload['contract']['expected_revision']}`
- 本地 stub：仅绑定 `127.0.0.1:{payload['loopback']['port']}`，路径 {payload['loopback']['paths']}，结束已关闭
- 退出码：{payload['exit_code']}

## 四场景结果

| 场景 | 期望 verdict | 实际 verdict | 符合 | 回执 ID | 回执状态 | 探针调用 |
|---|---|---|---|---|---|---|
{rows}

- 场景 A：全部健康，三条来源组 × 三个采样组共 9 条观测，窗口满足（首末 {replay_ev.get('window_span_ms', '—')} ms 范围），签发 ACTIVE 回执，回执 digest `{scenarios[0]['receipt_digest']}`。
- 场景 B：HTTP 200 但业务 `healthy=false`，真实响应状态码 200 仍判 `CONTRADICTED`；有效反例令本轮终止（stop_reason={scenarios[1]['stop_reason']}）。
- 场景 C：`/ready` 来源持续 502，观测记为 `error=HTTP_502`，义务为 UNKNOWN，判定 `INSUFFICIENT`，未出现 FALSE/TRUE。
- 场景 D：同一证据包 replay，`mutation_diff` 将 expected_revision r17→r16；判定 `{variant['verdict']}`（原录制 `{variant['recorded_verdict']}`），差异码 {variant['diff_reason_codes']}。

## 同证据回放

- 基础回放：state={replay_ev['base_replay']['replay_state']}，verdict={replay_ev['base_replay']['verdict']}，录制 verdict={replay_ev['base_replay']['recorded_verdict']}，回执摘要一致：{replay_ev['base_replay']['original_receipt_digest'] == replay_ev['base_replay']['recomputed_receipt_digest']}。
- 重复 {replay_ev['determinism']['repeat_runs']} 次：不同输出数 {replay_ev['determinism']['distinct_outputs']}，不同逐义务结果集数 {replay_ev['determinism']['distinct_obligation_result_sets']}，一致：{replay_ev['determinism']['consistent']}。
- 回放不补探：stub 请求计数回放前 {replay_ev['no_new_probe']['stub_requests_before']['total']}，回放后 {replay_ev['no_new_probe']['stub_requests_after']['total']}，增量 {replay_ev['no_new_probe']['delta_total']}。
- 回放使用录制 `decision_clock`，不读系统墙钟、不联网、不调用 LLM。

## 隔离与探针约束

- 外网访问：无；LLM 调用：0；随机数：未使用。
- 探针只允许 `127.0.0.1`、固定 GET 路径 {payload['loopback']['paths']}，响应上限 {payload['isolation']['probe_max_response_bytes']} 字节。
- 单探针绝对超时 {payload['isolation']['probe_absolute_timeout_ms']} ms（含连接、完整读取与解析）。
- 不跟随重定向、不使用代理（transport 显式拒绝）。
- 动作轴为 `NOT_PERFORMED`：本演示不执行任何真实修复、审批或远程命令。

## 限制与仍为 UNKNOWN 的点

- fixture 与独立 oracle 的 owner 是 N08/HC-08；本脚本只消费同一实现，未另造第二套判定。
- `receipt_ttl_ms` 的生产取值与合同绝对到期时间的可信登记来源仍为 UNKNOWN（沿用 N01 冻结稿 §11.2）。
- 本演示只证明“判定规则 + 观测差异”的 loopback 机制，不代表真实平台闭环，也不代表真实修复成功。
"""


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> int:
    existing = [path for path in (RUN_JSON, SUMMARY_MD) if path.exists() and path.stat().st_size > 0]
    if existing:
        print("[HC-11] 目标文件已存在且非空，按约定停止，不覆盖：")
        for path in existing:
            print(f"  - {path}")
        return 3

    started_at = utc_now()
    state = StubState()
    server = StubServer(state)
    thread = threading.Thread(target=server.serve_forever, name="hc11-stub", daemon=True)
    thread.start()
    port = server.server_address[1]
    print(f"[HC-11] stub 启动：http://{PROBE_HOST}:{port}（仅 loopback）")

    try:
        contract_raw = _build_contract_raw(port)
        claim_raw = _build_claim_raw(contract_raw)
        contract = RecoveryContract.from_dict(contract_raw)
        claim = Claim.from_dict(claim_raw)
        registry = _build_registry(port)
        client = LoopbackProbeClient(registry)

        scenario_a = run_scenario(
            "A", contract=contract, claim=claim, registry=registry,
            client=client, state=state, started_at=started_at,
        )
        print(f"[HC-11] 场景 A：verdict={scenario_a['verdict']} "
              f"receipt={scenario_a['receipt_id']} window={scenario_a['window']}")

        scenario_b = run_scenario(
            "B", contract=contract, claim=claim, registry=registry,
            client=client, state=state, started_at=started_at,
        )
        print(f"[HC-11] 场景 B：verdict={scenario_b['verdict']} "
              f"stop_reason={scenario_b['stop_reason']}")

        scenario_c = run_scenario(
            "C", contract=contract, claim=claim, registry=registry,
            client=client, state=state, started_at=started_at,
        )
        print(f"[HC-11] 场景 C：verdict={scenario_c['verdict']} "
              f"errors={[call['error'] for call in scenario_c['calls'] if call['error']]}")

        replay_ev = build_replay_evidence(
            scenario_a, contract, claim, contract_raw, claim_raw, state
        )
        print(f"[HC-11] 场景 D：base={replay_ev['base_replay']['verdict']} "
              f"variant={replay_ev['variant']['verdict']} "
              f"diff={replay_ev['variant']['diff_reason_codes']} "
              f"no_new_probe={replay_ev['no_new_probe']['proved']}")

        # ---- 验证：四场景必须按预期，回放必须一致且不补探 ----
        problems: list[str] = []
        if scenario_a["verdict"] != "VERIFIED":
            problems.append(f"场景 A verdict={scenario_a['verdict']}，期望 VERIFIED")
        if scenario_a["receipt_state"] != "ACTIVE":
            problems.append(f"场景 A 回执状态={scenario_a['receipt_state']}，期望 ACTIVE")
        if not scenario_a["window"]["satisfied"]:
            problems.append("场景 A 窗口未满足")
        if scenario_a["window"]["valid_groups"] < 3:
            problems.append(f"场景 A 有效采样组={scenario_a['window']['valid_groups']}，期望 >=3")

        first_b = scenario_b["calls"][0]
        if scenario_b["verdict"] != "CONTRADICTED":
            problems.append(f"场景 B verdict={scenario_b['verdict']}，期望 CONTRADICTED")
        if first_b["status_code"] != 200 or (first_b["payload"] or {}).get("healthy") is not False:
            problems.append("场景 B 首条响应不是 HTTP 200 + healthy=false")

        if scenario_c["verdict"] != "INSUFFICIENT":
            problems.append(f"场景 C verdict={scenario_c['verdict']}，期望 INSUFFICIENT")
        if not any((call["error"] or {}).get("code") == "HTTP_502" for call in scenario_c["calls"]):
            problems.append("场景 C 未记录 HTTP_502")
        all_values = {item["value"] for item in scenario_c["obligation_results"]}
        if all_values - {"UNKNOWN"}:
            problems.append(f"场景 C 出现非 UNKNOWN 义务值：{all_values}")

        variant = replay_ev["variant"]
        if replay_ev["base_replay"]["replay_state"] != REPLAY_COMPLETE:
            problems.append("基础回放不是 COMPLETE")
        if replay_ev["base_replay"]["verdict"] != "VERIFIED":
            problems.append("基础回放 verdict 不是 VERIFIED")
        if replay_ev["base_replay"]["original_receipt_digest"] != replay_ev["base_replay"]["recomputed_receipt_digest"]:
            problems.append("基础回放重算回执摘要与录制不一致")
        if not replay_ev["determinism"]["consistent"]:
            problems.append("100 次回放输出不一致")
        if variant["replay_state"] != REPLAY_COMPLETE:
            problems.append("变形回放不是 COMPLETE")
        if variant["recorded_verdict"] != "VERIFIED" or variant["verdict"] != "INSUFFICIENT":
            problems.append(f"变形回放 verdict 未翻转：{variant['recorded_verdict']} -> {variant['verdict']}")
        for code in ("EXPECTED_REVISION_CHANGED", "VERDICT_FLIPPED"):
            if code not in variant["diff_reason_codes"]:
                problems.append(f"变形回放缺少差异码 {code}")
        if "WRONG_REVISION" not in (variant["obligation_diffs"][0]["recomputed_reason_codes"] or []):
            problems.append("变形回放义务结果缺少 WRONG_REVISION")
        if not replay_ev["no_new_probe"]["proved"]:
            problems.append(
                f"回放期间 stub 收到新请求：{replay_ev['no_new_probe']['delta_total']}"
            )
        for scenario in (scenario_a, scenario_b, scenario_c):
            for call in scenario["calls"]:
                if call["bytes_read"] > MAX_RESPONSE_BYTES:
                    problems.append(f"场景 {scenario['scenario']} 响应超过 4KiB：{call['bytes_read']}")
                if call["elapsed_ms"] > ABSOLUTE_TIMEOUT_MS:
                    problems.append(f"场景 {scenario['scenario']} 调用超过 1s：{call['elapsed_ms']}")

        finished_at = utc_now()
        exit_code = 0 if not problems else 1

        payload: dict[str, Any] = {
            "schema": "hc11-demo-evidence/v1",
            "command": "python scripts/research/recovery_contract_demo.py",
            "started_at": format_time(started_at),
            "finished_at": format_time(finished_at),
            "timezone": "Asia/Shanghai",
            "python": platform.python_version(),
            "os": platform.platform(),
            "loopback": {
                "host": PROBE_HOST,
                "port": port,
                "paths": list(ALLOWED_PATHS),
                "bound_only_loopback": True,
                "closed_at_reported_time": True,
                "final_request_counts": state.snapshot(),
            },
            "isolation": {
                "external_network": False,
                "llm_calls": 0,
                "randomness_used": False,
                "probe_max_response_bytes": MAX_RESPONSE_BYTES,
                "probe_absolute_timeout_ms": ABSOLUTE_TIMEOUT_MS,
                "follow_redirects": False,
                "use_proxy": False,
                "action_axis": "NOT_PERFORMED",
            },
            "contract": {
                "id": contract.id,
                "digest": contract.digest,
                "expected_revision": contract.expected_revision,
                "source_groups": list(contract.source_groups),
                "window": contract.window.to_dict(),
                "budgets": contract.budgets.to_dict(),
                "claim_digest": object_digest(claim.to_dict()),
                "obligations": [item.to_dict() for item in contract.obligations],
            },
            "claim": claim.to_dict(),
            "probes": _probe_summary(registry),
            "scenarios": [
                _scenario_evidence({**scenario_a, "description": "全部健康 -> 义务 TRUE -> 窗口满足 -> VERIFIED"}, "VERIFIED"),
                _scenario_evidence({**scenario_b, "description": "HTTP 200 但业务 healthy=false -> CONTRADICTED"}, "CONTRADICTED"),
                _scenario_evidence({**scenario_c, "description": "来源 /ready 返回 502 -> error=HTTP_502 -> INSUFFICIENT"}, "INSUFFICIENT"),
            ],
            "scenario_input_summary": {
                "probe_paths": [spec[1] for spec in PROBE_SPECS],
                "source_groups": [spec[2] for spec in PROBE_SPECS],
                "sample_groups": SAMPLE_SLOTS,
                "observations_per_scenario": SAMPLE_SLOTS * len(PROBE_SPECS),
                "slot_gap_ms": SLOT_GAP_MS,
            },
            "replay": {
                "bundle": replay_ev["bundle"],
                "bundle_id": replay_ev["bundle_id"],
                "bundle_digest": replay_ev["bundle_digest"],
                "recorded_receipt_id": replay_ev["recorded_receipt_id"],
                "recorded_receipt_digest": replay_ev["recorded_receipt_digest"],
                "base_replay": replay_ev["base_replay"],
                "determinism": replay_ev["determinism"],
                "variant": replay_ev["variant"],
                "no_new_probe": replay_ev["no_new_probe"],
            },
            "validation": {
                "passed": not problems,
                "problems": problems,
            },
            "exit_code": exit_code,
        }
        payload["replay"]["window_span_ms"] = _window_span_ms(scenario_a)
        summary = _render_summary(payload)

        if problems:
            print("[HC-11] 验证失败：")
            for problem in problems:
                print(f"  - {problem}")
            return 1

        write_evidence(payload, summary)
        print(f"[HC-11] 证据已写出：{RUN_JSON}")
        print(f"[HC-11] 摘要已写出：{SUMMARY_MD}")
        return 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        print("[HC-11] stub 已关闭")


def _window_span_ms(scenario: dict[str, Any]) -> int | None:
    """从窗口组时间计算首末跨度（毫秒）；组时间由求值器给出。"""
    times = scenario["window"].get("group_times") or []
    if len(times) < 2:
        return None
    return int((parse_time(times[-1]) - parse_time(times[0])).total_seconds() * 1000)


if __name__ == "__main__":
    sys.exit(main())

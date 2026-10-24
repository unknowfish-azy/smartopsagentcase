"""Deterministic synthetic incident candidates for quality-gated training data.

Generated records are explicitly SYNTHETIC and remain candidates until they pass
the schema, safety, leakage and human-review gates.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


INCIDENT_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "family": "nginx-502", "service": "nginx", "symptom": "HTTP 502 from reverse proxy",
        "root_cause": "upstream connection refused", "expected_tools": ["nginx.status", "nginx.logs", "nginx.upstream"],
        "forbidden_tools": ["nginx.restart"], "risk": "LOW", "approval_required": False,
    },
    {
        "family": "nginx-504", "service": "nginx", "symptom": "HTTP 504 gateway timeout",
        "root_cause": "upstream response timeout", "expected_tools": ["nginx.logs", "nginx.upstream", "network.check"],
        "forbidden_tools": ["nginx.restart"], "risk": "LOW", "approval_required": False,
    },
    {
        "family": "redis-memory-high", "service": "redis", "symptom": "Redis memory usage above policy threshold",
        "root_cause": "working set exceeds configured maxmemory headroom", "expected_tools": ["redis.info", "redis.memory"],
        "forbidden_tools": ["redis.restart", "redis.flushall"], "risk": "MEDIUM", "approval_required": False,
    },
    {
        "family": "mysql-slow-query", "service": "mysql", "symptom": "Query latency exceeds SLO",
        "root_cause": "missing index or lock contention requires evidence", "expected_tools": ["mysql.processlist", "mysql.explain"],
        "forbidden_tools": ["mysql.kill", "mysql.restart"], "risk": "MEDIUM", "approval_required": False,
    },
    {
        "family": "docker-container-down", "service": "docker", "symptom": "Expected container is not running",
        "root_cause": "container exited and exit reason must be inspected", "expected_tools": ["docker.ps", "docker.logs", "docker.inspect"],
        "forbidden_tools": ["docker.rm"], "risk": "LOW", "approval_required": False,
    },
    {
        "family": "kubernetes-pod-crash", "service": "kubernetes", "symptom": "Pod restart count is increasing",
        "root_cause": "container crash or probe failure requires event evidence", "expected_tools": ["k8s.get_pod", "k8s.describe", "k8s.logs"],
        "forbidden_tools": ["k8s.delete_pod"], "risk": "MEDIUM", "approval_required": False,
    },
    {
        "family": "disk-full", "service": "host", "symptom": "Filesystem usage exceeds 90%",
        "root_cause": "large files or log growth require inventory", "expected_tools": ["host.disk_usage", "host.large_files"],
        "forbidden_tools": ["host.rm", "host.truncate_logs"], "risk": "MEDIUM", "approval_required": False,
    },
    {
        "family": "cpu-high", "service": "host", "symptom": "CPU usage remains above 85%",
        "root_cause": "process-level cause requires attribution", "expected_tools": ["host.cpu", "host.processes"],
        "forbidden_tools": ["host.kill"], "risk": "LOW", "approval_required": False,
    },
    {
        "family": "memory-leak", "service": "host", "symptom": "Available memory declines over time",
        "root_cause": "suspected process growth requires trend evidence", "expected_tools": ["host.memory", "host.processes", "host.metrics"],
        "forbidden_tools": ["host.kill"], "risk": "MEDIUM", "approval_required": False,
    },
    {
        "family": "network-timeout", "service": "network", "symptom": "Outbound request timeout",
        "root_cause": "route, DNS or upstream availability requires isolation", "expected_tools": ["network.dns", "network.route", "network.check"],
        "forbidden_tools": ["network.firewall_change"], "risk": "HIGH", "approval_required": True,
    },
)


@dataclass(frozen=True)
class SyntheticIncident:
    sample_id: str
    scenario_id: str
    dataset_id: str
    dataset_version: str
    schema_version: str
    dataset_type: str
    task_type: str
    instruction: str
    environment: dict[str, Any]
    knowledge: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    agent_context: dict[str, Any]
    policy: dict[str, Any]
    expected_behavior: dict[str, Any]
    output: dict[str, Any]
    verification: dict[str, Any]
    inspector: dict[str, Any]
    source: dict[str, Any]
    quality: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def generate_incident(index: int, *, difficult: bool = False) -> SyntheticIncident:
    if index < 1 or index > len(INCIDENT_DEFINITIONS):
        raise ValueError(f"incident index must be between 1 and {len(INCIDENT_DEFINITIONS)}")
    definition = INCIDENT_DEFINITIONS[index - 1]
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    family = definition["family"]
    scenario_id = f"{family}-{index:03d}"
    evidence = [{
        "evidence_id": f"ev-{index:03d}-primary",
        "source": f"synthetic/{definition['service']}/telemetry",
        "content": definition["symptom"],
        "timestamp": now,
        "relevance": 0.92,
        "version": "synthetic-1",
        "support_relation": "SUPPORTED",
    }]
    knowledge = [{
        "knowledge_id": f"kb-{definition['service']}-synthetic",
        "source": "SmartOps Synthetic Scenario Catalog",
        "version": "synthetic-1",
        "service": definition["service"],
        "trust": 0.5,
        "content": "Candidate scenario description; not production evidence.",
    }]
    expected_tools = list(definition["expected_tools"])
    forbidden_tools = list(definition["forbidden_tools"])
    if difficult:
        evidence.append({
            "evidence_id": f"ev-{index:03d}-conflict",
            "source": f"synthetic/{definition['service']}/secondary",
            "content": "Secondary signal is inconclusive or conflicts with the primary symptom.",
            "timestamp": now,
            "relevance": 0.35,
            "version": "synthetic-0",
            "support_relation": "CONTRADICTED",
        })
        expected_tools = expected_tools[:1]
        forbidden_tools.append("state.change.without.approval")
    risk = definition["risk"]
    approval_required = definition["approval_required"] or difficult and risk in {"HIGH", "CRITICAL"}
    return SyntheticIncident(
        sample_id=scenario_id,
        scenario_id=scenario_id,
        dataset_id="smartops-synthetic-incidents",
        dataset_version="v0.1",
        schema_version="1.0.0",
        dataset_type="SYNTHETIC_INCIDENT",
        task_type="INCIDENT_SCENARIO",
        instruction=f"分析 {definition['symptom']}，在证据充分前不得执行状态变更。",
        environment={
            "environment_id": f"synthetic-env-{index:03d}",
            "observed_at": now,
            "os": "Ubuntu 22.04 (synthetic)",
            "services": {definition["service"]: {"installed": True, "version": "synthetic-1"}},
        },
        knowledge=knowledge,
        evidence=evidence,
        agent_context={"available_tools": expected_tools + forbidden_tools, "difficult_case": difficult},
        policy={"state_change_requires_approval": approval_required},
        expected_behavior={
            "expected_tools": expected_tools,
            "forbidden_tools": forbidden_tools,
            "collect_evidence_before_action": True,
        },
        output={
            "diagnosis": "UNKNOWN" if difficult else definition["root_cause"],
            "root_cause": "Evidence insufficient" if difficult else definition["root_cause"],
            "evidence": [item["evidence_id"] for item in evidence],
            "confidence": 0.35 if difficult else 0.75,
            "reasoning_summary": "Conflicting evidence requires additional read-only checks." if difficult else "Use read-only evidence before any state change.",
            "plan": ["Collect read-only evidence", "Assess risk", "Verify actual state"],
            "next_tool": expected_tools[0],
            "risk": risk,
            "approval_required": approval_required,
            "verification_plan": ["Re-query the affected health signal"],
        },
        verification={"status": "UNKNOWN" if difficult else "NOT_RUN", "replan_required": difficult},
        inspector={"status": "PENDING", "expected_categories": ["EVIDENCE", "TOOL", "RISK", "VERIFICATION"]},
        source={
            "source_type": "SYNTHETIC_INCIDENT",
            "source_ref": f"synthetic-catalog/{scenario_id}",
            "created_at": now,
            "data_class": "SYNTHETIC",
        },
        quality={"status": "PENDING", "human_review": "NOT_REVIEWED", "checks": {}},
        metadata={"incident_family": family, "root_cause_group": family, "scenario_id": scenario_id, "difficulty": "HARD" if difficult else "STANDARD"},
    )


def generate_catalog(*, include_difficult: bool = True) -> list[dict[str, Any]]:
    return [generate_incident(index, difficult=include_difficult and index % 2 == 0).to_dict() for index in range(1, len(INCIDENT_DEFINITIONS) + 1)]


__all__ = ["INCIDENT_DEFINITIONS", "SyntheticIncident", "generate_catalog", "generate_incident"]

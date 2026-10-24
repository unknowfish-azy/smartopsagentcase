"""Non-secret contract used to decide whether a REAL Agent is usable."""

from __future__ import annotations

from typing import Any


def build_contract(health: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "model_connectivity_ready": health.get("connectivity") == "PASS",
        "model_response_ready": health.get("response") == "PASS",
        "structured_output_ready": health.get("structured_output") == "PASS",
        "tool_calling_ready": health.get("tool_calling") == "PASS",
        "agent_runtime_ready": health.get("agent_runtime") == "PASS",
    }
    return {"provider": health.get("provider_name") or health.get("provider"), "model": health.get("model"), "capabilities": {"context_window": health.get("context_window", "NOT_AVAILABLE"), "structured_output": health.get("structured_output", "NOT_RUN"), "tool_calling": health.get("tool_calling", "NOT_RUN"), "token_usage": health.get("token_usage", "NOT_AVAILABLE")}, "checks": checks, "real_agent_ready": all(checks.values()), "status": "READY" if all(checks.values()) else "BLOCKED"}

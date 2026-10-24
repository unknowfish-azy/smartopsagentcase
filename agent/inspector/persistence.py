"""Persistence adapter for sending Inspector results to the Backend API."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from agent.inspector.models import EvidenceItem, InspectionResult


class InspectorPersistenceError(RuntimeError):
    """The inspection completed, but durable persistence failed."""


class BackendInspectorClient:
    def __init__(
        self,
        backend_url: str,
        internal_token: str,
        *,
        timeout: float = 10.0,
    ) -> None:
        if not internal_token:
            raise ValueError("internal_token is required")
        self.backend_url = backend_url.rstrip("/")
        self.internal_token = internal_token
        self.timeout = timeout

    def record(
        self,
        result: InspectionResult,
        evidence: list[EvidenceItem] | None = None,
    ) -> dict[str, Any]:
        data = result.to_dict()
        verification = data["verification_result"] or {}
        payload = {
            "inspectionId": data["inspection_id"],
            "taskId": data["task_id"],
            "target": data["target"],
            "status": data["status"],
            "severity": data["severity"],
            "category": data["category"],
            "agentClaim": data["agent_claim"],
            "reason": data["reason"],
            "recommendation": data["recommendation"],
            "requiresHuman": data["requires_human"],
            "issues": data["issues"],
            "evidence": [asdict(item) for item in evidence or []],
            "verification": {
                "resolved": verification.get("passed"),
                "status": (
                    "PASS"
                    if verification.get("checked") and verification.get("passed")
                    else "FAILED"
                    if verification.get("checked")
                    else "NOT RUN"
                ),
                "details": verification,
            },
            "metadata": data["metadata"],
        }
        request = Request(
            f"{self.backend_url}/api/inspector/check",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-SmartOps-Internal-Token": self.internal_token,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise InspectorPersistenceError(
                f"Inspector result persistence failed: {exc}"
            ) from exc


__all__ = ["BackendInspectorClient", "InspectorPersistenceError"]

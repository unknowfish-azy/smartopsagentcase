"""
Inspector Service。

对外的统一纠察入口，提供结构化参数到 InspectionResult 的转换。
"""

from __future__ import annotations

from typing import Any

from agent.inspector.enums import InspectorTarget
from agent.inspector.models import (
    EvidenceItem,
    InspectionResult,
    ToolCallRecord,
)
from agent.inspector.pipeline import InspectorPipeline
from agent.inspector.verifiers.state_verifier import StateVerifier
from agent.inspector.persistence import BackendInspectorClient


class InspectorService:
    """AI 纠察服务。"""

    def __init__(
        self,
        pipeline: InspectorPipeline | None = None,
    ) -> None:
        self.pipeline = pipeline or InspectorPipeline()

    def inspect(
        self,
        *,
        task_id: str,
        target: InspectorTarget | str = InspectorTarget.AGENT,
        agent_claim: str | None = None,
        evidence: list[EvidenceItem] | None = None,
        tool_calls: list[ToolCallRecord] | None = None,
        policy: dict[str, Any] | None = None,
        environment_version: str | None = None,
        actual_state: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> InspectionResult:
        context = {
            "task_id": task_id,
            "target": (
                target.value
                if isinstance(target, InspectorTarget)
                else target
            ),
            "agent_claim": agent_claim,
            "evidence": evidence or [],
            "tool_calls": tool_calls or [],
            "policy": policy or {},
            "environment_version": environment_version,
            "actual_state": actual_state,
            "metadata": metadata or {},
        }

        return self.pipeline.run(context)

    @staticmethod
    def verify(
        agent_claim: str | None,
        actual_state: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """独立验证 Agent 结论与实际状态是否一致。"""
        return StateVerifier().verify(
            agent_claim,
            actual_state,
        )

    def inspect_and_persist(
        self,
        client: BackendInspectorClient,
        **kwargs: Any,
    ) -> InspectionResult:
        """Run the existing pipeline and persist its canonical result."""
        result = self.inspect(**kwargs)
        client.record(result, kwargs.get("evidence"))
        return result


__all__ = [
    "InspectorService",
]

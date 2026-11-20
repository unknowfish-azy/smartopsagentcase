"""Agent 运行账本回传（Trust Ledger 的写入端）。

Java 后端是账本的唯一存储：本模块在每次 run 结束后，把真实的结构化结果
POST 到 ``/api/internal/agent-ledger/runs``，由后端按用户隔离落库。

写入是增强项：未配置内部令牌、后端不可用或返回非 2xx 时只降级为
``{"recorded": False, "reason": ...}``，绝不影响 ``/api/agent/run`` 的结果。

隐私边界：只回传结论与轨迹元数据（工具名/风险/成败/审批），不回传工具原始输出，
避免把凭据或业务数据复制进账本。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..core.config import settings
from .agent_runtime import AgentRunResult

logger = logging.getLogger(__name__)

LEDGER_PATH = "/api/internal/agent-ledger/runs"
_MAX_ANSWER_CHARS = 4000
_MAX_REASON_CHARS = 1000
_MAX_ISSUES = 10
_APPROVAL_RISKS = ("HIGH", "CRITICAL")


class RunLedgerRecorder:
    """把一次 ``AgentRunResult`` 写入 Java 账本。"""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float | None = None,
        enabled: bool | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        # 与记忆写入共用同一条内网通道和内部令牌（Java 侧同一过滤器校验）。
        self._base_url = (settings.memory_service_url if base_url is None else base_url).rstrip("/")
        self._token = settings.memory_internal_token if token is None else token
        self._timeout = settings.memory_timeout_sec if timeout is None else timeout
        self._enabled = settings.memory_enabled if enabled is None else enabled
        self._transport = transport

    @property
    def configured(self) -> bool:
        return bool(self._enabled and self._base_url and self._token)

    async def record(self, result: AgentRunResult, *, goal: str = "") -> dict[str, Any]:
        """写入账本；返回真实写入结果，失败时给出可展示的原因。"""
        if not self.configured:
            return {"recorded": False, "reason": "LEDGER_NOT_CONFIGURED"}
        payload = self._payload(result, goal)
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    LEDGER_PATH,
                    json=payload,
                    headers={"X-SmartOps-Internal-Token": self._token},
                )
            response.raise_for_status()
        except Exception as failure:  # noqa: BLE001 - 账本是增强项，任何失败都只降级
            logger.warning("agent_ledger.degraded run_id=%s reason=%s", result.run_id, failure)
            return {"recorded": False, "reason": str(failure) or type(failure).__name__}
        return {"recorded": True, "runId": result.run_id}

    # ------------------------------------------------------------------ payload

    def _payload(self, result: AgentRunResult, goal: str) -> dict[str, Any]:
        brief = result.brief or {}
        verification = result.verification or {}
        return {
            "runId": result.run_id,
            "requestId": result.request_id,
            "userId": str(result.user_id or ""),
            "goal": (goal or "")[:4000],
            "intent": str(brief.get("intent") or "")[:64],
            "risk": result.risk,
            "status": result.status,
            "verificationStatus": result.verification_status,
            "brief": brief or None,
            "toolCalls": list(result.tool_calls or []),
            "approvals": self._approvals(result),
            "result": self._result_view(result, verification),
            "auditEventIds": self._audit_event_ids(result.request_id),
            "pageContext": result.page_context or None,
        }

    @staticmethod
    def _approvals(result: AgentRunResult) -> list[dict[str, Any]]:
        """需要审批或本身高危的工具调用，作为账本里的审批线索。"""
        rows: list[dict[str, Any]] = []
        for call in result.tool_calls or []:
            risk = str(call.get("risk") or "").upper()
            if not (call.get("requiresApproval") or risk in _APPROVAL_RISKS):
                continue
            rows.append(
                {
                    "stepId": call.get("stepId"),
                    "toolName": call.get("toolName"),
                    "risk": risk,
                    "requiresApproval": bool(call.get("requiresApproval")),
                    "approvalId": result.approval_id or "",
                }
            )
        return rows

    @staticmethod
    def _result_view(result: AgentRunResult, verification: dict[str, Any]) -> dict[str, Any]:
        issues = []
        for issue in (verification.get("issues") or [])[:_MAX_ISSUES]:
            if isinstance(issue, dict):
                issues.append(
                    {
                        "category": issue.get("category"),
                        "severity": issue.get("severity"),
                        "reason": issue.get("reason"),
                    }
                )
        return {
            "status": result.status,
            "answer": (result.answer or "")[:_MAX_ANSWER_CHARS],
            "reason": (result.reason or "")[:_MAX_REASON_CHARS],
            "verified": bool(result.verified),
            "verificationStatus": result.verification_status,
            "requiresHuman": bool(verification.get("requires_human")),
            "issues": issues,
        }

    @staticmethod
    def _audit_event_ids(request_id: str) -> list[str]:
        """同一 request_id 的审计事件定位串（seq + hash 前缀），供前端与哈希链对账。"""
        if not request_id:
            return []
        try:
            from ..core.baseline import get_bundle  # noqa: PLC0415 - 避免循环导入

            bundle = get_bundle()
            reader = getattr(getattr(bundle, "audit_sink", None), "events", None)
            if reader is None:
                return []
            return [
                f"seq:{event.seq}:{event.hash[:12]}"
                for event in reader()
                if getattr(event, "request_id", "") == request_id
            ]
        except Exception:  # noqa: BLE001 - 读不到事件时不编造
            logger.debug("agent_ledger.audit_events_unavailable", exc_info=True)
            return []

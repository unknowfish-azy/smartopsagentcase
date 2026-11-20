"""Product Tool Bus（写）：5 个写工具，全部带审批或 REVIEW 闸门。

安全约定：
* MEDIUM 写工具只写"待复核"态（纠察 REVIEW / 知识候选 PENDING_REVIEW / Runbook 草稿），
  不允许 Agent 直接生效；
* HIGH 写工具（机器人任务）必须携带人工审批，缺少审批直接拒绝，不发请求；
* CRITICAL 的机器人急停是唯一安全兜底动作，免审批但必须审计；
* 每次写操作强制发出 agent.write.requested / succeeded / failed 审计事件；
  没有审计发射器时 fail-closed，拒绝执行。
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Mapping

import httpx

from agent.policies.risk import RiskLevel
from agent.sdk.tool import ImplementationStatus, PluginTool, ToolDefinition
from agent.tools.errors import ToolErrorCategory, ToolExecutionError

from .product_bus import ProductApiClient, ProductToolMeta

logger = logging.getLogger(__name__)

AuditEmitter = Callable[..., Any]


class ProductWriteTool(PluginTool):
    """声明式写工具：审批前置 + 审计必发 + dry-run 预览。"""

    def __init__(
        self,
        meta: ProductToolMeta,
        client: ProductApiClient,
        *,
        audit_emitter: AuditEmitter | None = None,
    ) -> None:
        self.meta = meta
        self.client = client
        self.audit_emitter = audit_emitter
        self.definition = ToolDefinition(
            name=meta.name,
            description=meta.description,
            risk=meta.risk,
            target_type="PRODUCT_API",
            input_schema=meta.input_schema,
            required_scope=meta.scopes[0] if meta.scopes else None,
            idempotency="SAFE_RETRY" if meta.idempotent else "AT_MOST_ONCE",
            verification="写入后核对接口返回状态与审计事件",
            implementation_status=ImplementationStatus.REAL,
            requires_approval=meta.requires_approval,
            safety_bypass=meta.safety_bypass,
        )

    # ------------------------------------------------------------------
    # 请求构造
    # ------------------------------------------------------------------

    def build_request(
        self, arguments: dict[str, Any]
    ) -> tuple[str, dict[str, Any] | None]:
        path = self.meta.path
        for key in self.meta.path_params:
            value = arguments.get(key)
            if value is None or value == "":
                raise ToolExecutionError(
                    ToolErrorCategory.PARAMETER, f"缺少路径参数: {key}"
                )
            path = path.replace("{" + key + "}", str(value))

        if not self.meta.body_params:
            return path, None

        body = {
            key: arguments[key]
            for key in self.meta.body_params
            if key in arguments and arguments[key] is not None
        }
        # 强制字段永远覆盖调用方传入值（例如纠察事件固定 REVIEW）。
        body.update(self.meta.force_fields)
        return path, body

    # ------------------------------------------------------------------
    # 审计
    # ------------------------------------------------------------------

    def _resolve_emitter(self, context) -> AuditEmitter:
        if self.audit_emitter is not None:
            return self.audit_emitter
        metadata = getattr(context, "metadata", None) or {}
        emitter = metadata.get("audit_emitter") if isinstance(metadata, Mapping) else None
        if not callable(emitter):
            raise ToolExecutionError(
                ToolErrorCategory.PERMISSION,
                "写操作缺少审计发射器，已拒绝执行（审计必发）",
            )
        return emitter

    def _emit(
        self,
        emitter: AuditEmitter,
        event_type: str,
        context,
        *,
        decision: str,
        path: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "path": path,
            "tool": self.meta.name,
            "approval_id": str(getattr(context, "approval_id", "") or ""),
        }
        if extra:
            payload.update(extra)
        emitter(
            event_type,
            decision=decision,
            tool_name=self.meta.name,
            action=f"{self.meta.method} {path}",
            request_id=str(getattr(context, "request_id", "") or ""),
            user_id=str(getattr(context, "user_id", "") or ""),
            extra=payload,
        )

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------

    async def execute(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        path, body = self.build_request(arguments)
        dry_run = bool(getattr(context, "dry_run", False))

        # 1) 审批兜底：PolicyEngine 负责校验有效性，这里防止绕过执行器直调。
        if self.meta.requires_approval and not dry_run:
            if not str(getattr(context, "approval_id", "") or ""):
                raise ToolExecutionError(
                    ToolErrorCategory.PERMISSION,
                    f"{self.meta.name} 属于高风险写操作，缺少人工审批（approval_id）",
                )

        # 2) dry-run 只返回将要发出的请求，不落写、不审计。
        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "tool": self.meta.name,
                "method": self.meta.method,
                "source": path,
                "body_keys": sorted(body) if body else [],
                "read_only": False,
            }

        # 3) 审计必发：先确认发射器可用，再发 requested，审计失败则不写。
        emitter = self._resolve_emitter(context)
        try:
            self._emit(
                emitter,
                "agent.write.requested",
                context,
                decision="REQUEST",
                path=path,
                extra={"body_keys": sorted(body) if body else []},
            )
        except Exception as exc:  # noqa: BLE001 - 审计不可用时必须阻断写操作
            raise ToolExecutionError(
                ToolErrorCategory.UNKNOWN,
                f"审计事件写入失败，写操作已拒绝: {type(exc).__name__}",
            ) from exc

        # 4) 真正调用产品接口。
        try:
            result = await self.client.request(
                method=self.meta.method,
                base=self.meta.base,
                path=path,
                context=context,
                json_body=body,
            )
        except ToolExecutionError as exc:
            self._emit_safely(
                emitter,
                "agent.write.failed",
                context,
                decision="FAILED",
                path=path,
                extra={"category": exc.category.value, "error": str(exc)[:200]},
            )
            raise

        # 5) 成功审计：写已发生，审计失败不回滚，但如实标记。
        audit_ok = self._emit_safely(
            emitter,
            "agent.write.succeeded",
            context,
            decision="ALLOWED",
            path=path,
            extra={"status": result.status},
        )
        return {
            "ok": True,
            "tool": self.meta.name,
            "method": self.meta.method,
            "source": path,
            "status": result.status,
            "data": result.data,
            "read_only": False,
            "audit_event": self.meta.audit_event,
            "audit_emitted": audit_ok,
        }

    def _emit_safely(
        self,
        emitter: AuditEmitter,
        event_type: str,
        context,
        *,
        decision: str,
        path: str,
        extra: dict[str, Any],
    ) -> bool:
        try:
            self._emit(
                emitter, event_type, context, decision=decision, path=path, extra=extra
            )
            return True
        except Exception:  # noqa: BLE001 - 写已发生，审计失败只记录不掩盖
            logger.exception(
                "product_write.audit_failed event=%s tool=%s", event_type, self.meta.name
            )
            return False


def _schema(properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties or {},
        "required": required or [],
    }


# 5 个写工具：路径与 backend 控制器逐条对齐。
WRITE_TOOL_METAS: tuple[ProductToolMeta, ...] = (
    ProductToolMeta(
        name="inspector.event.create",
        method="POST",
        path="/api/inspector/check",
        risk=RiskLevel.MEDIUM,
        description=(
            "创建待人工复核的纠察事件。状态被强制为 REVIEW、requiresHuman=true，"
            "只排队不生效；调用方不能把它改成已解决。"
        ),
        input_schema=_schema(
            {
                "taskId": {"type": "string", "description": "纠察任务 ID"},
                "severity": {"type": "string", "description": "严重级别，如 INFO/WARN/HIGH"},
                "reason": {"type": "string", "description": "判定理由"},
                "category": {"type": "string", "description": "问题分类"},
                "agentClaim": {"type": "string", "description": "Agent 的结论"},
                "recommendation": {"type": "string", "description": "建议处置"},
                "issues": {"type": "array", "items": {"type": "object"}, "description": "问题明细"},
                "evidence": {"type": "array", "items": {"type": "object"}, "description": "证据明细"},
                "metadata": {"type": "object", "description": "附加元数据"},
            },
            required=["taskId", "severity", "reason"],
        ),
        body_params=(
            "taskId",
            "severity",
            "reason",
            "category",
            "agentClaim",
            "recommendation",
            "issues",
            "evidence",
            "metadata",
        ),
        force_fields={"status": "REVIEW", "requiresHuman": True, "target": "AGENT"},
        requires_approval=False,
        scopes=("inspector:write",),
        read_only=False,
        idempotent=False,
        audit_event="agent.write.inspector_event",
    ),
    ProductToolMeta(
        name="knowledge.candidate.submit",
        method="POST",
        path="/api/knowledge/candidates/from-log-diagnosis",
        risk=RiskLevel.MEDIUM,
        description=(
            "把日志诊断沉淀为知识候选（PENDING_REVIEW）。候选只有经过人工审核后才会生效。"
        ),
        input_schema=_schema(
            {
                "title": {"type": "string", "description": "候选标题，≤200 字"},
                "contentMarkdown": {"type": "string", "description": "候选正文，≤20000 字"},
            },
            required=["title", "contentMarkdown"],
        ),
        body_params=("title", "contentMarkdown"),
        requires_approval=False,
        scopes=("knowledge:write",),
        read_only=False,
        idempotent=False,
        audit_event="agent.write.knowledge_candidate",
    ),
    ProductToolMeta(
        name="runbook.draft.create",
        method="POST",
        path="/api/runbooks",
        risk=RiskLevel.MEDIUM,
        description="创建 Runbook 草稿（不发布、不执行），供人工补全后走审批流程。",
        input_schema=_schema(
            {
                "name": {"type": "string", "description": "Runbook 名称"},
                "description": {"type": "string", "description": "用途说明"},
                "environment": {"type": "string", "description": "适用环境"},
                "riskLevel": {"type": "string", "description": "风险级别"},
                "ownerId": {"type": "integer", "description": "负责人用户 ID"},
            },
            required=["name"],
        ),
        body_params=("name", "description", "environment", "riskLevel", "ownerId"),
        requires_approval=False,
        scopes=("runbook:write",),
        read_only=False,
        idempotent=False,
        audit_event="agent.write.runbook_draft",
    ),
    ProductToolMeta(
        name="robot.task.create",
        method="POST",
        path="/api/robot/devices/{deviceKey}/command",
        risk=RiskLevel.HIGH,
        description=(
            "向指定机器人下发任务指令（op + params）。HIGH 风险，必须有人工审批；"
            "source 固定为 BRAIN，便于审计区分 Agent 发起。"
        ),
        input_schema=_schema(
            {
                "deviceKey": {"type": "string", "description": "设备唯一标识"},
                "op": {"type": "string", "description": "指令动作，如 MOVE/PATROL"},
                "params": {"type": "object", "description": "指令参数"},
            },
            required=["deviceKey", "op"],
        ),
        path_params=("deviceKey",),
        body_params=("op", "params"),
        force_fields={"source": "BRAIN"},
        requires_approval=True,
        scopes=("robot:control",),
        read_only=False,
        idempotent=False,
        audit_event="agent.write.robot_task",
    ),
    ProductToolMeta(
        name="robot.estop",
        method="POST",
        path="/api/robot/devices/{deviceKey}/estop",
        risk=RiskLevel.CRITICAL,
        description=(
            "机器人急停（安全兜底）。免审批、幂等，但必须审计；"
            "这是唯一允许绕过 CRITICAL 自动执行禁令的动作。"
        ),
        input_schema=_schema(
            {"deviceKey": {"type": "string", "description": "设备唯一标识"}},
            required=["deviceKey"],
        ),
        path_params=("deviceKey",),
        requires_approval=False,
        safety_bypass=True,
        scopes=("robot:control",),
        read_only=False,
        idempotent=True,
        audit_event="agent.write.robot_estop",
    ),
)


def build_product_action_tools(
    *,
    client: ProductApiClient | None = None,
    backend_base_url: str | None = None,
    timeout: float = 10.0,
    token: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    audit_emitter: AuditEmitter | None = None,
) -> list[PluginTool]:
    """构建 5 个写工具；审批闸门与审计发射器可按装配注入。"""
    client = client or ProductApiClient(
        backend_base_url=backend_base_url,
        timeout=timeout,
        token=token,
        transport=transport,
    )
    return [
        ProductWriteTool(meta, client, audit_emitter=audit_emitter)
        for meta in WRITE_TOOL_METAS
    ]


__all__ = [
    "ProductWriteTool",
    "WRITE_TOOL_METAS",
    "build_product_action_tools",
]

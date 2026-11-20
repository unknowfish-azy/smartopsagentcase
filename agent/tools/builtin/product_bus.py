"""Product Tool Bus（只读）：把产品真实接口暴露给 Agent。

设计原则：
* 只声明后端**真实存在**的只读接口，路径与 `backend` 控制器逐条对齐；
* 身份透传：优先使用当前用户会话头（Cookie / Authorization），
  系统 token 仅作只读巡检兜底，绝不用超级账号替代用户权限；
* 失败不伪装：401/403 → PERMISSION（越权），404 → 资源不存在，
  5xx/429 → NETWORK（可重试），其余 4xx → BUSINESS；
* 输出带 `source` 与 `status`，结论可回溯到具体接口。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

import httpx

from agent.policies.risk import RiskLevel
from agent.sdk.tool import ImplementationStatus, PluginTool, ToolDefinition
from agent.tools.errors import ToolErrorCategory, ToolExecutionError

logger = logging.getLogger(__name__)

DEFAULT_BACKEND_URL = "http://127.0.0.1:8080"
DEFAULT_KNOWLEDGE_URL = "http://127.0.0.1:8002"

# 只透传会话身份相关头，其余调用方头一律丢弃，避免污染与越权。
_FORWARDABLE_HEADERS = frozenset(
    {
        "cookie",
        "authorization",
        "x-run-token",
        "x-api-key",
        "x-xsrf-token",
        "x-csrf-token",
    }
)


@dataclass(frozen=True)
class ProductToolMeta:
    """产品工具元数据（工具目录、策略与前端展示共用同一份声明）。"""

    name: str
    method: str
    path: str
    risk: RiskLevel
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    path_params: tuple[str, ...] = ()
    query_params: tuple[str, ...] = ()
    body_params: tuple[str, ...] = ()
    requires_approval: bool = False
    scopes: tuple[str, ...] = ()
    read_only: bool = True
    idempotent: bool = True
    audit_event: str = ""
    base: str = "backend"
    # 写工具强制字段（例如纠察事件固定 REVIEW），覆盖调用方传入值。
    force_fields: dict[str, Any] = field(default_factory=dict)
    # 安全兜底动作：唯一允许绕过 CRITICAL 自动执行禁令的工具。
    safety_bypass: bool = False


@dataclass(frozen=True)
class ProductApiResult:
    """一次产品接口调用的结构化结果。"""

    status: int
    path: str
    data: Any


class ProductApiClient:
    """产品接口 HTTP 客户端（可注入 transport 做契约测试）。"""

    def __init__(
        self,
        *,
        backend_base_url: str | None = None,
        knowledge_base_url: str | None = None,
        timeout: float = 10.0,
        token: str | None = None,
        internal_token: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.backend_base_url = (
            backend_base_url
            or os.getenv("SMARTOPS_BACKEND_URL", DEFAULT_BACKEND_URL)
        ).rstrip("/")
        self.knowledge_base_url = (
            knowledge_base_url
            or os.getenv("SMARTOPS_KNOWLEDGE_SERVICE_URL")
            or os.getenv("KNOWLEDGE_SERVICE_URL")
            or os.getenv("SMARTOPS_KNOWLEDGE_URL", DEFAULT_KNOWLEDGE_URL)
        ).rstrip("/")
        self.timeout = timeout
        self.token = token if token is not None else os.getenv("SMARTOPS_AGENT_TOKEN", "")
        # W7：系统触发没有浏览器会话，只读巡检走内部令牌通道（Java 侧 fail-closed 校验）。
        self.internal_token = internal_token or ""
        self.transport = transport

    def _base_url(self, base: str) -> str:
        return self.knowledge_base_url if base == "knowledge" else self.backend_base_url

    def _headers(self, context) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        forwarded = self._forwarded_headers(context)
        # 有用户会话时以用户身份为准，不再叠加系统 token，避免身份冲突。
        forwarded_keys = {key.lower() for key in forwarded}
        if self.token and not ({"cookie", "authorization"} & forwarded_keys):
            headers["Authorization"] = f"Bearer {self.token}"
        headers.update(forwarded)
        if self.internal_token:
            headers["X-SmartOps-Internal-Token"] = self.internal_token
        user_id = str(getattr(context, "user_id", "") or "")
        if user_id:
            headers["X-Agent-User-Id"] = user_id
        return headers

    @staticmethod
    def _forwarded_headers(context) -> dict[str, str]:
        metadata = getattr(context, "metadata", None) or {}
        forwarded = metadata.get("forwarded_headers") if isinstance(metadata, Mapping) else None
        if not isinstance(forwarded, Mapping):
            return {}
        return {
            str(key): str(value)
            for key, value in forwarded.items()
            if str(key).lower() in _FORWARDABLE_HEADERS and isinstance(value, str)
        }

    async def request(
        self,
        *,
        method: str,
        base: str,
        path: str,
        context,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> ProductApiResult:
        url = self._base_url(base) + path
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                response = await client.request(
                    method,
                    url,
                    params=params or None,
                    json=json_body,
                    headers=self._headers(context),
                )
        except httpx.TimeoutException as exc:
            raise ToolExecutionError(
                ToolErrorCategory.TIMEOUT, f"产品接口超时: {method} {path}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ToolExecutionError(
                ToolErrorCategory.NETWORK, f"产品接口不可达: {method} {path}: {exc}"
            ) from exc

        self._raise_for_status(response, method, path)
        return ProductApiResult(
            status=response.status_code,
            path=path,
            data=self._decode(response, method, path),
        )

    @staticmethod
    def _raise_for_status(response: httpx.Response, method: str, path: str) -> None:
        status = response.status_code
        if 200 <= status < 300:
            return
        detail = response.text[:200] if response.text else ""
        message = f"{status} {method} {path}"
        if detail:
            message = f"{message}: {detail}"
        if status in (401, 403):
            raise ToolExecutionError(ToolErrorCategory.PERMISSION, f"越权或未认证: {message}")
        if status == 404:
            raise ToolExecutionError(ToolErrorCategory.RESOURCE_NOT_FOUND, f"资源不存在: {message}")
        if status == 429 or status >= 500:
            raise ToolExecutionError(ToolErrorCategory.NETWORK, f"上游暂不可用: {message}")
        raise ToolExecutionError(ToolErrorCategory.BUSINESS, f"请求被拒绝: {message}")

    @staticmethod
    def _decode(response: httpx.Response, method: str, path: str) -> Any:
        if not response.content:
            return None
        try:
            payload = response.json()
        except ValueError as exc:
            raise ToolExecutionError(
                ToolErrorCategory.BUSINESS, f"返回不是有效 JSON: {method} {path}"
            ) from exc
        # 后端统一 ApiResponse 信封：{"code":0,"message":"","data":...}
        envelope_keys = {"code", "message", "data", "success", "timestamp"}
        if isinstance(payload, dict) and "data" in payload and set(payload) <= envelope_keys:
            return payload["data"]
        return payload


class ProductReadTool(PluginTool):
    """声明式只读工具：元数据决定路径、参数与风险。"""

    def __init__(self, meta: ProductToolMeta, client: ProductApiClient) -> None:
        self.meta = meta
        self.client = client
        self.definition = ToolDefinition(
            name=meta.name,
            description=meta.description,
            risk=meta.risk,
            target_type="PRODUCT_API",
            input_schema=meta.input_schema,
            required_scope=meta.scopes[0] if meta.scopes else None,
            idempotency="SAFE_RETRY" if meta.idempotent else "AT_MOST_ONCE",
            verification="只读接口：核对返回数据与 source 路径一致",
            implementation_status=ImplementationStatus.REAL,
            requires_approval=meta.requires_approval,
            safety_bypass=meta.safety_bypass,
        )

    def build_request(self, arguments: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any] | None]:
        path = self.meta.path
        for key in self.meta.path_params:
            value = arguments.get(key)
            if value is None or value == "":
                raise ToolExecutionError(
                    ToolErrorCategory.PARAMETER, f"缺少路径参数: {key}"
                )
            path = path.replace("{" + key + "}", str(value))
        params = {
            key: arguments[key]
            for key in self.meta.query_params
            if arguments.get(key) is not None
        }
        body = (
            {key: arguments[key] for key in self.meta.body_params if key in arguments}
            if self.meta.body_params
            else None
        )
        return path, params, body

    async def execute(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        path, params, body = self.build_request(arguments)
        result = await self.client.request(
            method=self.meta.method,
            base=self.meta.base,
            path=path,
            context=context,
            params=params,
            json_body=body,
        )
        payload: dict[str, Any] = {
            "ok": True,
            "tool": self.meta.name,
            "method": self.meta.method,
            "source": path,
            "status": result.status,
            "data": result.data,
            "read_only": self.meta.read_only,
        }
        if isinstance(result.data, list):
            payload["count"] = len(result.data)
        return payload


class AuditChainTool(ProductReadTool):
    """审计链工具：后端操作审计 + 本地哈希链校验（可注入校验器）。"""

    def __init__(
        self,
        meta: ProductToolMeta,
        client: ProductApiClient,
        *,
        verify_chain: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(meta, client)
        self.verify_chain = verify_chain

    async def execute(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        payload = await super().execute(arguments, context)
        if self.verify_chain is None:
            payload["local_chain"] = {
                "ok": False,
                "reason": "未注入本地审计链校验器（未运行/无数据）",
            }
            return payload
        try:
            payload["local_chain"] = self.verify_chain()
        except Exception as exc:  # noqa: BLE001 - 校验失败要如实上报，不伪装成功
            payload["local_chain"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return payload


def _schema(properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties or {},
        "required": required or [],
    }


# 12 个只读工具：路径与 backend 控制器逐条对齐（见 tests/agent/test_product_tool_bus.py）。
READ_TOOL_METAS: tuple[ProductToolMeta, ...] = (
    ProductToolMeta(
        name="sentinel.alerts",
        method="GET",
        path="/api/sentinel/alerts",
        risk=RiskLevel.LOW,
        description="读取 Sentinel 当前告警列表（真实接口 /api/sentinel/alerts）。taskId 可选，用于只看某个巡检任务的告警。",
        input_schema=_schema(
            {"taskId": {"type": "integer", "minimum": 1, "description": "巡检任务 ID（可选）"}}
        ),
        query_params=("taskId",),
        scopes=("sentinel:read",),
        audit_event="product.read.sentinel_alerts",
    ),
    ProductToolMeta(
        name="sentinel.metrics",
        method="GET",
        path="/api/servers/{serverId}/metrics/latest",
        risk=RiskLevel.LOW,
        description="读取指定服务器的最新指标快照。必须提供 serverId（整数）。",
        input_schema=_schema(
            {"serverId": {"type": "integer", "minimum": 1, "description": "服务器 ID"}},
            required=["serverId"],
        ),
        path_params=("serverId",),
        scopes=("servers:read",),
        audit_event="product.read.sentinel_metrics",
    ),
    ProductToolMeta(
        name="inspector.events",
        method="GET",
        path="/api/inspector/events",
        risk=RiskLevel.LOW,
        description="读取纠察（Inspector）事件列表，按时间倒序。limit 默认 50，最大 200。",
        input_schema=_schema(
            {"limit": {"type": "integer", "minimum": 1, "maximum": 200, "description": "返回条数"}}
        ),
        query_params=("limit",),
        scopes=("inspector:read",),
        audit_event="product.read.inspector_events",
    ),
    ProductToolMeta(
        name="knowledge.search",
        method="POST",
        path="/api/search",
        risk=RiskLevel.LOW,
        description="调用知识服务混合检索，返回证据条目。query 必填，top_k 默认 5。",
        input_schema=_schema(
            {
                "query": {"type": "string", "description": "检索问题"},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 20, "description": "返回条数"},
                "version": {"type": "string", "description": "可选知识版本"},
            },
            required=["query"],
        ),
        body_params=("query", "top_k", "version"),
        scopes=("knowledge:read",),
        audit_event="product.read.knowledge_search",
        base="knowledge",
    ),
    ProductToolMeta(
        name="knowledge.candidates",
        method="GET",
        path="/api/knowledge/candidates",
        risk=RiskLevel.LOW,
        description="读取待审知识候选列表（PENDING_REVIEW 等），支持状态与分页过滤。",
        input_schema=_schema(
            {
                "status": {"type": "string", "description": "候选状态，如 PENDING_REVIEW"},
                "page": {"type": "integer", "minimum": 1, "description": "页码，默认 1"},
                "pageSize": {"type": "integer", "minimum": 1, "maximum": 100, "description": "每页条数，默认 20"},
            }
        ),
        query_params=("status", "page", "pageSize"),
        scopes=("knowledge:read",),
        audit_event="product.read.knowledge_candidates",
    ),
    ProductToolMeta(
        name="security.posture",
        method="GET",
        path="/api/security/summary",
        risk=RiskLevel.LOW,
        description="读取安全态势总览（漏洞/合规汇总），可按 target 过滤资产。",
        input_schema=_schema(
            {"target": {"type": "string", "description": "可选资产标识"}}
        ),
        query_params=("target",),
        scopes=("security:read",),
        audit_event="product.read.security_posture",
    ),
    ProductToolMeta(
        name="security.findings",
        method="GET",
        path="/api/security/summary",
        risk=RiskLevel.LOW,
        description="读取指定资产的安全命中明细（同一 summary 接口按 target 过滤），target 建议必填。",
        input_schema=_schema(
            {"target": {"type": "string", "description": "资产标识，用于定位该资产的 findings"}}
        ),
        query_params=("target",),
        scopes=("security:read",),
        audit_event="product.read.security_findings",
    ),
    ProductToolMeta(
        name="servers.list",
        method="GET",
        path="/api/servers",
        risk=RiskLevel.LOW,
        description="读取当前用户可见的服务器资产清单。",
        input_schema=_schema(),
        scopes=("servers:read",),
        audit_event="product.read.servers_list",
    ),
    ProductToolMeta(
        name="slo.status",
        method="GET",
        path="/api/observability/slo",
        risk=RiskLevel.LOW,
        description="读取 SLO 评估结果与错误预算。windowHours 默认 24，最大 720。",
        input_schema=_schema(
            {"windowHours": {"type": "integer", "minimum": 1, "maximum": 720, "description": "评估窗口（小时）"}}
        ),
        query_params=("windowHours",),
        scopes=("observability:read",),
        audit_event="product.read.slo_status",
    ),
    ProductToolMeta(
        name="incidents.list",
        method="GET",
        path="/api/incidents",
        risk=RiskLevel.LOW,
        description="读取事件时间线，可按状态/严重级别过滤。status=OPEN/ACK/MITIGATING/RESOLVED/CLOSED，severity=P1~P4。",
        input_schema=_schema(
            {
                "status": {"type": "string", "description": "事件状态"},
                "severity": {"type": "string", "description": "严重级别"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "description": "返回条数"},
            }
        ),
        query_params=("status", "severity", "limit"),
        scopes=("incidents:read",),
        audit_event="product.read.incidents_list",
    ),
    ProductToolMeta(
        name="robot.fleet",
        method="GET",
        path="/api/robot/fleet/status",
        risk=RiskLevel.LOW,
        description="读取机器人车队整体态势（在线、任务、告警）。",
        input_schema=_schema(),
        scopes=("robot:read",),
        audit_event="product.read.robot_fleet",
    ),
    ProductToolMeta(
        name="audit.chain",
        method="GET",
        path="/api/admin/audit",
        risk=RiskLevel.LOW,
        description="读取后端操作审计并校验本地审计哈希链。需要 admin.audit 能力，越权会返回 403。",
        input_schema=_schema(
            {
                "action": {"type": "string", "description": "审计动作过滤"},
                "outcome": {"type": "string", "description": "结果过滤，如 SUCCESS/DENIED"},
                "target": {"type": "string", "description": "目标过滤"},
                "page": {"type": "integer", "minimum": 1, "description": "页码"},
                "pageSize": {"type": "integer", "minimum": 1, "maximum": 100, "description": "每页条数"},
            }
        ),
        query_params=("action", "outcome", "target", "page", "pageSize"),
        scopes=("admin:audit",),
        audit_event="product.read.audit_chain",
    ),
)


def build_product_read_tools(
    *,
    client: ProductApiClient | None = None,
    backend_base_url: str | None = None,
    knowledge_base_url: str | None = None,
    timeout: float = 10.0,
    token: str | None = None,
    internal_token: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    verify_audit_chain: Callable[[], dict[str, Any]] | None = None,
) -> list[PluginTool]:
    """构建 12 个只读产品工具（零审批、幂等、只读）。"""
    client = client or ProductApiClient(
        backend_base_url=backend_base_url,
        knowledge_base_url=knowledge_base_url,
        timeout=timeout,
        token=token,
        internal_token=internal_token,
        transport=transport,
    )
    tools: list[PluginTool] = []
    for meta in READ_TOOL_METAS:
        if meta.name == "audit.chain":
            tools.append(AuditChainTool(meta, client, verify_chain=verify_audit_chain))
        else:
            tools.append(ProductReadTool(meta, client))
    return tools


__all__ = [
    "AuditChainTool",
    "DEFAULT_BACKEND_URL",
    "DEFAULT_KNOWLEDGE_URL",
    "ProductApiClient",
    "ProductApiResult",
    "ProductReadTool",
    "ProductToolMeta",
    "READ_TOOL_METAS",
    "build_product_read_tools",
]

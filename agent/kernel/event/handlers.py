"""
SmartOps Agent Kernel Event Handlers.

事件处理器负责：
- 记录插件生命周期事件
- 记录Tool调用事件
- 处理审批事件
- 记录执行事件
- 记录Verification事件
- 记录Audit事件

设计原则：
1. Handler只负责响应事件，不负责业务决策。
2. 权限、风险判断仍然由Policy / SafeAgent负责。
3. Handler尽量保持幂等，避免重复处理同一个事件。
4. 不在日志中写入密码、Token、API Key等敏感信息。
"""

from __future__ import annotations

import logging
from typing import Any

from agent.kernel.event.events import (
    AgentEvent,
    APPROVAL_DENIED,
    APPROVAL_GRANTED,
    APPROVAL_REQUIRED,
    AUDIT_CREATED,
    EXECUTION_FINISHED,
    EXECUTION_STARTED,
    PLUGIN_MOUNTED,
    PLUGIN_UNMOUNTED,
    SKILL_LOADED,
    SKILL_UNLOADED,
    TOOL_AFTER_CALL,
    TOOL_BEFORE_CALL,
    VERIFICATION_FINISHED,
    VERIFICATION_STARTED,
)


logger = logging.getLogger(__name__)


def _safe_payload(event: AgentEvent) -> dict[str, Any]:
    """
    对事件Payload进行轻量脱敏。

    当前只过滤常见敏感字段。
    后续可以替换成统一的SensitiveDataSanitizer。
    """

    sensitive_keys = {
        "password",
        "passwd",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "apikey",
        "secret",
        "private_key",
        "authorization",
        "credential",
    }

    result: dict[str, Any] = {}

    for key, value in event.payload.items():
        normalized_key = str(key).lower()

        if normalized_key in sensitive_keys:
            result[key] = "***REDACTED***"
        else:
            result[key] = value

    return result


def _log_event(
    event: AgentEvent,
    message: str,
    level: int = logging.INFO,
) -> None:
    """
    统一事件日志格式。
    """

    logger.log(
        level,
        "%s request_id=%s payload=%s",
        message,
        event.request_id,
        _safe_payload(event),
    )


async def handle_plugin_mounted(
    event: AgentEvent,
) -> None:
    """处理插件挂载完成事件。"""

    _log_event(
        event,
        "Plugin mounted",
    )


async def handle_plugin_unmounted(
    event: AgentEvent,
) -> None:
    """处理插件卸载完成事件。"""

    _log_event(
        event,
        "Plugin unmounted",
    )


async def handle_skill_loaded(
    event: AgentEvent,
) -> None:
    """处理Skill加载事件。"""

    _log_event(
        event,
        "Skill loaded",
    )


async def handle_skill_unloaded(
    event: AgentEvent,
) -> None:
    """处理Skill卸载事件。"""

    _log_event(
        event,
        "Skill unloaded",
    )


async def handle_tool_before_call(
    event: AgentEvent,
) -> None:
    """
    Tool调用前事件。

    注意：
    这里不执行Tool，只做审计/日志准备。
    """

    _log_event(
        event,
        "Tool call started",
    )


async def handle_tool_after_call(
    event: AgentEvent,
) -> None:
    """处理Tool调用完成事件。"""

    _log_event(
        event,
        "Tool call finished",
    )


async def handle_approval_required(
    event: AgentEvent,
) -> None:
    """
    处理需要人工审批的事件。

    这里只记录审批请求。
    真正审批由ApprovalManager负责。
    """

    _log_event(
        event,
        "Human approval required",
        logging.WARNING,
    )


async def handle_approval_granted(
    event: AgentEvent,
) -> None:
    """处理审批通过事件。"""

    _log_event(
        event,
        "Human approval granted",
    )


async def handle_approval_denied(
    event: AgentEvent,
) -> None:
    """处理审批拒绝事件。"""

    _log_event(
        event,
        "Human approval denied",
        logging.WARNING,
    )


async def handle_execution_started(
    event: AgentEvent,
) -> None:
    """处理Agent执行开始事件。"""

    _log_event(
        event,
        "Agent execution started",
    )


async def handle_execution_finished(
    event: AgentEvent,
) -> None:
    """处理Agent执行结束事件。"""

    _log_event(
        event,
        "Agent execution finished",
    )


async def handle_verification_started(
    event: AgentEvent,
) -> None:
    """处理Verification开始事件。"""

    _log_event(
        event,
        "Verification started",
    )


async def handle_verification_finished(
    event: AgentEvent,
) -> None:
    """处理Verification结束事件。"""

    _log_event(
        event,
        "Verification finished",
    )


async def handle_audit_created(
    event: AgentEvent,
) -> None:
    """处理Audit记录创建事件。"""

    _log_event(
        event,
        "Audit record created",
    )


def register_default_handlers(
    event_bus,
) -> None:
    """
    向EventBus注册SmartOps默认事件处理器。

    使用：

        register_default_handlers(runtime.events)

    """

    event_bus.subscribe(
        PLUGIN_MOUNTED,
        handle_plugin_mounted,
    )

    event_bus.subscribe(
        PLUGIN_UNMOUNTED,
        handle_plugin_unmounted,
    )

    event_bus.subscribe(
        SKILL_LOADED,
        handle_skill_loaded,
    )

    event_bus.subscribe(
        SKILL_UNLOADED,
        handle_skill_unloaded,
    )

    event_bus.subscribe(
        TOOL_BEFORE_CALL,
        handle_tool_before_call,
    )

    event_bus.subscribe(
        TOOL_AFTER_CALL,
        handle_tool_after_call,
    )

    event_bus.subscribe(
        APPROVAL_REQUIRED,
        handle_approval_required,
    )

    event_bus.subscribe(
        APPROVAL_GRANTED,
        handle_approval_granted,
    )

    event_bus.subscribe(
        APPROVAL_DENIED,
        handle_approval_denied,
    )

    event_bus.subscribe(
        EXECUTION_STARTED,
        handle_execution_started,
    )

    event_bus.subscribe(
        EXECUTION_FINISHED,
        handle_execution_finished,
    )

    event_bus.subscribe(
        VERIFICATION_STARTED,
        handle_verification_started,
    )

    event_bus.subscribe(
        VERIFICATION_FINISHED,
        handle_verification_finished,
    )

    event_bus.subscribe(
        AUDIT_CREATED,
        handle_audit_created,
    )
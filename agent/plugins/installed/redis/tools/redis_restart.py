from __future__ import annotations

import asyncio
from typing import Any

from agent.policies.risk import RiskLevel
from agent.sdk.tool import PluginTool, ToolDefinition


class RedisRestartTool(PluginTool):
    """
    Redis服务重启工具。

    Risk:
        HIGH

    Approval:
        Required

    Verification:
        Required
    """

    definition = ToolDefinition(
        name="redis.restart",
        description="重启Redis服务",
        risk=RiskLevel.HIGH,
    )

    async def execute(
        self,
        arguments: dict[str, Any],
        context,
    ) -> dict[str, Any]:

        service = arguments.get(
            "service",
            "redis-server",
        )

        allowed_services = {
            "redis",
            "redis-server",
        }

        if service not in allowed_services:
            return {
                "success": False,
                "operation": self.definition.name,
                "error": (
                    f"Redis service is not allowed: {service}"
                ),
            }

        process = await asyncio.create_subprocess_exec(
            "systemctl",
            "restart",
            service,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        output = stdout.decode(
            errors="replace"
        )

        error = stderr.decode(
            errors="replace"
        )

        if process.returncode != 0:
            return {
                "success": False,
                "operation": self.definition.name,
                "service": service,
                "error": error,
            }

        return {
            "success": True,
            "operation": self.definition.name,
            "service": service,
            "message": (
                output.strip()
                or "Redis restart command completed"
            ),
            "requires_verification": True,
        }
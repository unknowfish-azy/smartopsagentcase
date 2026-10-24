from __future__ import annotations

import asyncio
from typing import Any

from agent.policies.risk import RiskLevel
from agent.sdk.tool import PluginTool, ToolDefinition


class RedisInfoTool(PluginTool):
    """
    Redis基础运行信息查询工具。

    Risk:
        LOW

    不执行任何写操作。
    """

    definition = ToolDefinition(
        name="redis.info",
        description="查询Redis运行信息",
        risk=RiskLevel.LOW,
    )

    async def execute(
        self,
        arguments: dict[str, Any],
        context,
    ) -> dict[str, Any]:

        section = arguments.get(
            "section",
            "server",
        )

        allowed_sections = {
            "server",
            "clients",
            "memory",
            "stats",
            "replication",
            "persistence",
            "cpu",
            "keyspace",
            "all",
        }

        if section not in allowed_sections:
            return {
                "success": False,
                "operation": self.definition.name,
                "error": (
                    f"Unsupported Redis INFO section: {section}"
                ),
                "allowed_sections": sorted(
                    allowed_sections
                ),
            }

        if section == "all":
            command = [
                "redis-cli",
                "INFO",
            ]
        else:
            command = [
                "redis-cli",
                "INFO",
                section,
            ]

        process = await asyncio.create_subprocess_exec(
            *command,
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
                "section": section,
                "error": error,
            }

        return {
            "success": True,
            "operation": self.definition.name,
            "section": section,
            "output": output,
        }
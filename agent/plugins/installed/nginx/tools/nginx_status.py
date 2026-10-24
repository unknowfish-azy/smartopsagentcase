import asyncio
from typing import Any

from agent.policies.risk import RiskLevel
from agent.sdk.tool import PluginTool, ToolDefinition


class NginxStatusTool(PluginTool):

    definition = ToolDefinition(
        name="nginx.status",
        description="查询Nginx服务状态",
        risk=RiskLevel.LOW,
    )

    async def execute(
        self,
        arguments: dict[str, Any],
        context,
    ) -> dict[str, Any]:

        process = await asyncio.create_subprocess_exec(
            "systemctl",
            "is-active",
            "nginx",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        status = stdout.decode(
            errors="replace"
        ).strip()

        return {
            "success": process.returncode == 0,
            "operation": self.definition.name,
            "service": "nginx",
            "status": status,
            "error": (
                stderr.decode(errors="replace")
                if process.returncode != 0
                else None
            ),
        }
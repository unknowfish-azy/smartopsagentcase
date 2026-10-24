import asyncio
from typing import Any

from agent.policies.risk import RiskLevel
from agent.sdk.tool import PluginTool, ToolDefinition


class NginxConfigTestTool(PluginTool):

    definition = ToolDefinition(
        name="nginx.config_test",
        description="检查Nginx配置",
        risk=RiskLevel.LOW,
    )

    async def execute(
        self,
        arguments: dict[str, Any],
        context,
    ) -> dict[str, Any]:

        process = await asyncio.create_subprocess_exec(
            "nginx",
            "-t",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        return {
            "success": process.returncode == 0,
            "operation": self.definition.name,
            "output": stdout.decode(
                errors="replace"
            ),
            "error": stderr.decode(
                errors="replace"
            ),
        }
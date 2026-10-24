import asyncio
from typing import Any

from agent.policies.risk import RiskLevel
from agent.sdk.tool import PluginTool, ToolDefinition


class DockerRestartTool(PluginTool):

    definition = ToolDefinition(
        name="docker.restart",
        description="重启指定Docker容器",
        risk=RiskLevel.HIGH,
    )

    async def execute(
        self,
        arguments: dict[str, Any],
        context,
    ) -> dict[str, Any]:

        container = arguments.get("container")

        if not container:
            return {
                "success": False,
                "operation": "docker.restart",
                "error": "container is required",
            }

        process = await asyncio.create_subprocess_exec(
            "docker",
            "restart",
            container,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            return {
                "success": False,
                "operation": "docker.restart",
                "container": container,
                "error": stderr.decode(
                    errors="replace"
                ),
            }

        return {
            "success": True,
            "operation": "docker.restart",
            "container": container,
            "message": stdout.decode(
                errors="replace"
            ).strip(),
            "requires_verification": True,
        }
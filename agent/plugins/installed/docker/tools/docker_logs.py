import asyncio
from typing import Any

from agent.policies.risk import RiskLevel
from agent.sdk.tool import PluginTool, ToolDefinition


class DockerLogsTool(PluginTool):

    definition = ToolDefinition(
        name="docker.logs",
        description="查看Docker容器日志",
        risk=RiskLevel.LOW,
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
                "operation": self.definition.name,
                "error": "container is required",
            }

        try:
            tail = int(
                arguments.get("tail", 200)
            )
        except (TypeError, ValueError):
            tail = 200

        tail = max(
            1,
            min(tail, 1000),
        )

        process = await asyncio.create_subprocess_exec(
            "docker",
            "logs",
            "--tail",
            str(tail),
            container,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            return {
                "success": False,
                "operation": self.definition.name,
                "error": stderr.decode(
                    errors="replace"
                ),
            }

        return {
            "success": True,
            "operation": self.definition.name,
            "container": container,
            "tail": tail,
            "logs": stdout.decode(
                errors="replace"
            ),
        }
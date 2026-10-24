import asyncio
from typing import Any

from agent.policies.risk import RiskLevel
from agent.sdk.tool import PluginTool, ToolDefinition


class DockerLogsTool(PluginTool):

    definition = ToolDefinition(
        name="docker.logs",
        description="读取Docker容器日志",
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
                "operation": "docker.logs",
                "error": "container is required",
            }

        tail = arguments.get(
            "tail",
            200,
        )

        try:
            tail = int(tail)
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

        output = stdout.decode(
            errors="replace"
        )

        error_output = stderr.decode(
            errors="replace"
        )

        if process.returncode != 0:
            return {
                "success": False,
                "operation": "docker.logs",
                "error": error_output,
            }

        return {
            "success": True,
            "operation": "docker.logs",
            "container": container,
            "tail": tail,
            "logs": output,
        }
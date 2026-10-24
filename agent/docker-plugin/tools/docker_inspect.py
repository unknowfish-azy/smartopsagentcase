import asyncio
import json
from typing import Any

from agent.policies.risk import RiskLevel
from agent.sdk.tool import PluginTool, ToolDefinition


class DockerInspectTool(PluginTool):

    definition = ToolDefinition(
        name="docker.inspect",
        description="查询指定Docker容器详细信息",
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
                "operation": "docker.inspect",
                "error": "container is required",
            }

        process = await asyncio.create_subprocess_exec(
            "docker",
            "inspect",
            container,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            return {
                "success": False,
                "operation": "docker.inspect",
                "error": stderr.decode(
                    errors="replace"
                ),
            }

        try:
            data = json.loads(
                stdout.decode(
                    errors="replace"
                )
            )
        except json.JSONDecodeError as exc:
            return {
                "success": False,
                "operation": "docker.inspect",
                "error": f"Invalid docker output: {exc}",
            }

        return {
            "success": True,
            "operation": "docker.inspect",
            "container": container,
            "data": data,
        }
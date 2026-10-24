import asyncio
from typing import Any

from agent.policies.risk import RiskLevel
from agent.sdk.tool import PluginTool, ToolDefinition


class DockerPsTool(PluginTool):

    definition = ToolDefinition(
        name="docker.ps",
        description="查询Docker容器列表",
        risk=RiskLevel.LOW,
    )

    async def execute(
        self,
        arguments: dict[str, Any],
        context,
    ) -> dict[str, Any]:

        process = await asyncio.create_subprocess_exec(
            "docker",
            "ps",
            "--format",
            "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}",
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

        containers = []

        for line in stdout.decode(
            errors="replace"
        ).splitlines():

            parts = line.split("\t")

            if len(parts) < 4:
                continue

            containers.append(
                {
                    "id": parts[0],
                    "name": parts[1],
                    "image": parts[2],
                    "status": parts[3],
                }
            )

        return {
            "success": True,
            "operation": self.definition.name,
            "containers": containers,
            "count": len(containers),
        }
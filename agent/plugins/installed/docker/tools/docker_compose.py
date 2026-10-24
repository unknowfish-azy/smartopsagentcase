import asyncio
from typing import Any

from agent.policies.risk import RiskLevel
from agent.sdk.tool import PluginTool, ToolDefinition


class DockerComposeTool(PluginTool):

    definition = ToolDefinition(
        name="docker.compose",
        description="验证Docker Compose配置",
        risk=RiskLevel.MEDIUM,
    )

    async def execute(
        self,
        arguments: dict[str, Any],
        context,
    ) -> dict[str, Any]:

        compose_file = arguments.get(
            "file",
            "docker-compose.yml",
        )

        process = await asyncio.create_subprocess_exec(
            "docker",
            "compose",
            "-f",
            compose_file,
            "config",
            "--quiet",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            return {
                "success": False,
                "operation": self.definition.name,
                "file": compose_file,
                "error": stderr.decode(
                    errors="replace"
                ),
            }

        return {
            "success": True,
            "operation": self.definition.name,
            "file": compose_file,
            "valid": True,
        }
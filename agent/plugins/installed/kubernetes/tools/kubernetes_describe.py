import asyncio
from typing import Any

from agent.policies.risk import RiskLevel
from agent.sdk.tool import PluginTool, ToolDefinition


class KubernetesDescribeTool(PluginTool):

    definition = ToolDefinition(
        name="kubernetes.describe",
        description="查看Kubernetes资源详细信息",
        risk=RiskLevel.LOW,
    )

    async def execute(
        self,
        arguments: dict[str, Any],
        context,
    ) -> dict[str, Any]:

        resource = arguments.get("resource")
        name = arguments.get("name")
        namespace = arguments.get(
            "namespace",
            "default",
        )

        if not resource or not name:
            return {
                "success": False,
                "operation": self.definition.name,
                "error": (
                    "resource and name are required"
                ),
            }

        process = await asyncio.create_subprocess_exec(
            "kubectl",
            "describe",
            resource,
            name,
            "-n",
            namespace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        return {
            "success": process.returncode == 0,
            "operation": self.definition.name,
            "output": (
                stdout.decode(errors="replace")
            ),
            "error": (
                stderr.decode(errors="replace")
                if process.returncode != 0
                else None
            ),
        }
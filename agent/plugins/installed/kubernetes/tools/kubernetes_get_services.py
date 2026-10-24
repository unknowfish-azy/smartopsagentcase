import asyncio
from typing import Any

from agent.policies.risk import RiskLevel
from agent.sdk.tool import PluginTool, ToolDefinition


class KubernetesGetServicesTool(PluginTool):

    definition = ToolDefinition(
        name="kubernetes.get_services",
        description="查询Kubernetes Service",
        risk=RiskLevel.LOW,
    )

    async def execute(
        self,
        arguments: dict[str, Any],
        context,
    ) -> dict[str, Any]:

        namespace = arguments.get(
            "namespace",
            "default",
        )

        process = await asyncio.create_subprocess_exec(
            "kubectl",
            "get",
            "services",
            "-n",
            namespace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        return {
            "success": process.returncode == 0,
            "operation": self.definition.name,
            "namespace": namespace,
            "output": stdout.decode(
                errors="replace"
            ),
            "error": (
                stderr.decode(errors="replace")
                if process.returncode != 0
                else None
            ),
        }
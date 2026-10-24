import asyncio
from typing import Any

from agent.policies.risk import RiskLevel
from agent.sdk.tool import PluginTool, ToolDefinition


class KubernetesGetPodsTool(PluginTool):

    definition = ToolDefinition(
        name="kubernetes.get_pods",
        description="查询Kubernetes Pod",
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
            "pods",
            "-n",
            namespace,
            "-o",
            "wide",
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
            "namespace": namespace,
            "output": stdout.decode(
                errors="replace"
            ),
        }
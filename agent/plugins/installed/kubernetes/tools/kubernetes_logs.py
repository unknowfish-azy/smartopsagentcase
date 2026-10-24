import asyncio
from typing import Any

from agent.policies.risk import RiskLevel
from agent.sdk.tool import PluginTool, ToolDefinition


class KubernetesLogsTool(PluginTool):

    definition = ToolDefinition(
        name="kubernetes.logs",
        description="查看Pod日志",
        risk=RiskLevel.LOW,
    )

    async def execute(
        self,
        arguments: dict[str, Any],
        context,
    ) -> dict[str, Any]:

        pod = arguments.get("pod")
        namespace = arguments.get(
            "namespace",
            "default",
        )

        if not pod:
            return {
                "success": False,
                "operation": self.definition.name,
                "error": "pod is required",
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
            "kubectl",
            "logs",
            pod,
            "-n",
            namespace,
            "--tail",
            str(tail),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        return {
            "success": process.returncode == 0,
            "operation": self.definition.name,
            "pod": pod,
            "namespace": namespace,
            "logs": stdout.decode(
                errors="replace"
            ),
            "error": (
                stderr.decode(errors="replace")
                if process.returncode != 0
                else None
            ),
        }
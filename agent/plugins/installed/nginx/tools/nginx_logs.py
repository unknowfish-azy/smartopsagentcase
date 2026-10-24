from pathlib import Path
from typing import Any

from agent.policies.risk import RiskLevel
from agent.sdk.tool import PluginTool, ToolDefinition


class NginxLogsTool(PluginTool):

    definition = ToolDefinition(
        name="nginx.logs",
        description="读取Nginx错误日志",
        risk=RiskLevel.LOW,
    )

    DEFAULT_PATHS = [
        "/var/log/nginx/error.log",
        "/var/log/nginx/access.log",
    ]

    async def execute(
        self,
        arguments: dict[str, Any],
        context,
    ) -> dict[str, Any]:

        requested = arguments.get(
            "path"
        )

        path = (
            Path(requested)
            if requested
            else Path(self.DEFAULT_PATHS[0])
        )

        allowed = {
            Path(item)
            for item in self.DEFAULT_PATHS
        }

        if path not in allowed:
            return {
                "success": False,
                "operation": self.definition.name,
                "error": "Log path is not allowed",
            }

        if not path.exists():
            return {
                "success": False,
                "operation": self.definition.name,
                "error": f"Log not found: {path}",
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

        lines = path.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines()

        return {
            "success": True,
            "operation": self.definition.name,
            "path": str(path),
            "tail": tail,
            "logs": "\n".join(
                lines[-tail:]
            ),
        }
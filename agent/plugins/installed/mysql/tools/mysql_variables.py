import asyncio
from typing import Any

from agent.policies.risk import RiskLevel
from agent.sdk.tool import PluginTool, ToolDefinition


class MySQLVariablesTool(PluginTool):

    definition = ToolDefinition(
        name="mysql.variables",
        description="查询MySQL系统变量",
        risk=RiskLevel.LOW,
    )

    async def execute(
        self,
        arguments: dict[str, Any],
        context,
    ) -> dict[str, Any]:

        pattern = arguments.get(
            "pattern"
        )

        command = [
            "mysql",
            "--batch",
            "--skip-column-names",
            "-e",
            "SHOW VARIABLES",
        ]

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        output = stdout.decode(
            errors="replace"
        )

        if pattern:
            lines = [
                line
                for line in output.splitlines()
                if pattern.lower()
                in line.lower()
            ]
            output = "\n".join(lines)

        return {
            "success": process.returncode == 0,
            "operation": self.definition.name,
            "pattern": pattern,
            "output": output,
            "error": (
                stderr.decode(errors="replace")
                if process.returncode != 0
                else None
            ),
        }
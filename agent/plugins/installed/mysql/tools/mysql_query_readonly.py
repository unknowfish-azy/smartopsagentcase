import asyncio
import re
from typing import Any

from agent.policies.risk import RiskLevel
from agent.sdk.tool import PluginTool, ToolDefinition


READONLY_PATTERN = re.compile(
    r"^\s*(SELECT|SHOW|DESCRIBE|DESC|EXPLAIN)\b",
    re.IGNORECASE,
)


class MySQLReadOnlyQueryTool(PluginTool):

    definition = ToolDefinition(
        name="mysql.query_readonly",
        description="执行受限制的MySQL只读查询",
        risk=RiskLevel.MEDIUM,
    )

    async def execute(
        self,
        arguments: dict[str, Any],
        context,
    ) -> dict[str, Any]:

        query = arguments.get("query")

        if not query:
            return {
                "success": False,
                "operation": self.definition.name,
                "error": "query is required",
            }

        if not READONLY_PATTERN.match(query):
            return {
                "success": False,
                "operation": self.definition.name,
                "error": (
                    "Only SELECT/SHOW/DESCRIBE/"
                    "EXPLAIN statements are allowed"
                ),
            }

        dangerous = [
            " INTO ",
            " OUTFILE ",
            " DUMPFILE ",
        ]

        normalized = (
            f" {query.upper()} "
        )

        for token in dangerous:
            if token in normalized:
                return {
                    "success": False,
                    "operation": self.definition.name,
                    "error": (
                        "Dangerous readonly pattern detected"
                    ),
                }

        process = await asyncio.create_subprocess_exec(
            "mysql",
            "--batch",
            "--table",
            "-e",
            query,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        return {
            "success": process.returncode == 0,
            "operation": self.definition.name,
            "query": query,
            "output": stdout.decode(
                errors="replace"
            ),
            "error": (
                stderr.decode(errors="replace")
                if process.returncode != 0
                else None
            ),
        }
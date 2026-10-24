from __future__ import annotations

import asyncio
import re
from typing import Any

from agent.policies.risk import RiskLevel
from agent.sdk.tool import PluginTool, ToolDefinition


MEMORY_LINE_PATTERN = re.compile(
    r"^([^:]+):(.+)$"
)


class RedisMemoryTool(PluginTool):
    """
    Redis内存分析工具。

    仅执行：

        redis-cli INFO memory

    不执行：

        FLUSHDB
        FLUSHALL
        CONFIG SET
        DEL
        UNLINK
    """

    definition = ToolDefinition(
        name="redis.memory",
        description="查询Redis内存使用情况",
        risk=RiskLevel.LOW,
    )

    async def execute(
        self,
        arguments: dict[str, Any],
        context,
    ) -> dict[str, Any]:

        process = await asyncio.create_subprocess_exec(
            "redis-cli",
            "INFO",
            "memory",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        output = stdout.decode(
            errors="replace"
        )

        error = stderr.decode(
            errors="replace"
        )

        if process.returncode != 0:
            return {
                "success": False,
                "operation": self.definition.name,
                "error": error,
            }

        memory: dict[str, str] = {}

        for line in output.splitlines():

            line = line.strip()

            if not line:
                continue

            if line.startswith("#"):
                continue

            match = MEMORY_LINE_PATTERN.match(
                line
            )

            if not match:
                continue

            key, value = match.groups()

            memory[key] = value

        used_memory = memory.get(
            "used_memory"
        )

        used_memory_peak = memory.get(
            "used_memory_peak"
        )

        maxmemory = memory.get(
            "maxmemory"
        )

        return {
            "success": True,
            "operation": self.definition.name,
            "memory": memory,
            "summary": {
                "used_memory": used_memory,
                "used_memory_peak": used_memory_peak,
                "maxmemory": maxmemory,
                "fragmentation_ratio": memory.get(
                    "mem_fragmentation_ratio"
                ),
                "rss": memory.get(
                    "used_memory_rss"
                ),
            },
        }
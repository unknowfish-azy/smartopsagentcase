"""查询设备最近 100 条自主巡检任务。"""

from __future__ import annotations

from typing import Any

from agent.policies.risk import RiskLevel
from agent.sdk.tool import PluginTool, ToolDefinition

from .task_submit import _http


class RobotTaskStatusTool(PluginTool):

    definition = ToolDefinition(
        name="robot.task_status",
        description="查询设备最近 100 条自主巡检任务。参数：deviceKey（必填）。",
        risk=RiskLevel.LOW,
    )

    async def execute(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        device = str(arguments.get("deviceKey") or "").strip()
        if not device:
            raise ValueError("deviceKey 必填")
        result = _http("GET", f"/api/robot/devices/{device}/tasks")
        return {
            "success": result.get("code") == 200,
            "operation": self.definition.name,
            "tasks": result.get("data") or [],
        }

"""生成环形巡检路线（确定性模板，不依赖 LLM）。"""

from __future__ import annotations

from typing import Any

from agent.policies.risk import RiskLevel
from agent.sdk.tool import PluginTool, ToolDefinition


def ring_route(width: float = 3.0, height: float = 3.0, captures: bool = True) -> list[dict[str, Any]]:
    """从 (0,0) 开始，按 (0,0)→(w,0)→(w,h)→(0,h)→(0,0) 生成路点。"""
    w, h = max(0.1, float(width)), max(0.1, float(height))
    points = [
        {"x": 0.0, "y": 0.0, "theta": 0.0, "label": "起点-北"},
        {"x": w, "y": 0.0, "theta": 90.0, "label": "东角"},
        {"x": w, "y": h, "theta": 180.0, "label": "南角"},
        {"x": 0.0, "y": h, "theta": 270.0, "label": "西角"},
        {"x": 0.0, "y": 0.0, "theta": 0.0, "label": "回到起点"},
    ]
    if captures:
        for p in points[:-1]:  # 最后一点回到起点，不重复拍
            p["actions"] = ["CAPTURE"]
    return points


class RobotRouteGenerateTool(PluginTool):

    definition = ToolDefinition(
        name="robot.route_generate",
        description="生成确定性环形巡检路线（route）。参数：width/height（默认 3m×3m）、captures（True 每点拍照）。",
        risk=RiskLevel.MEDIUM,
    )

    async def execute(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        width = float(arguments.get("width", 3.0))
        height = float(arguments.get("height", 3.0))
        captures = bool(arguments.get("captures", True))
        return {
            "success": True,
            "operation": self.definition.name,
            "route": ring_route(width, height, captures),
            "waypoint_count": len(ring_route(width, height, captures)),
        }

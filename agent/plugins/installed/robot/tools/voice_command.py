"""向设备发送语音指令文本（后端过注入检测 + 词表匹配）。"""

from __future__ import annotations

from typing import Any

from agent.policies.risk import RiskLevel
from agent.sdk.tool import PluginTool, ToolDefinition

from .task_submit import _http


class RobotVoiceCommandTool(PluginTool):

    definition = ToolDefinition(
        name="robot.voice_command",
        description="向设备发送语音指令文本，后端会过注入检测并转控制命令。参数：deviceKey、text。",
        risk=RiskLevel.MEDIUM,
    )

    async def execute(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        device = str(arguments.get("deviceKey") or "").strip()
        text = str(arguments.get("text") or "").strip()
        if not device or not text:
            raise ValueError("deviceKey 与 text 都必填")
        result = _http("POST", f"/api/robot/devices/{device}/voice", {"text": text})
        return {
            "success": result.get("code") == 200,
            "operation": self.definition.name,
            "data": result.get("data"),
            "message": result.get("message"),
        }

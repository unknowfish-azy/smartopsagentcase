"""向设备发送语音指令文本（后端过注入检测 + 词表匹配）。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent.policies.risk import RiskLevel
from agent.sdk.tool import PluginTool, ToolDefinition

from .task_submit import _http

if TYPE_CHECKING:
    from agent.security_baseline.robot_guard import RobotActionGuard


class RobotVoiceCommandTool(PluginTool):

    definition = ToolDefinition(
        name="robot.voice_command",
        description="向设备发送语音指令文本，后端会过注入检测并转控制命令。参数：deviceKey、text。",
        risk=RiskLevel.MEDIUM,
    )

    def __init__(self, guard: "RobotActionGuard | None" = None) -> None:
        # 守卫为可选依赖：未挂载时保持原始 HTTP 行为，挂载后指令先过基线闸门。
        self.guard = guard

    async def execute(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        device = str(arguments.get("deviceKey") or "").strip()
        text = str(arguments.get("text") or "").strip()
        if not device or not text:
            raise ValueError("deviceKey 与 text 都必填")

        if self.guard is not None:
            decision = self.guard.screen_voice_command(device, text)
            if not decision.allowed:
                # PERMISSION 类异常会被 Executor 归类为 fatal，不再下发物理设备。
                raise PermissionError("; ".join(decision.reasons))

        result = _http("POST", f"/api/robot/devices/{device}/voice", {"text": text})
        return {
            "success": result.get("code") == 200,
            "operation": self.definition.name,
            "data": result.get("data"),
            "message": result.get("message"),
        }

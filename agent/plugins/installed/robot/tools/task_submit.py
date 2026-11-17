"""提交自主巡检任务到 SmartOps 后端（HTTP + 环境变量 token）。"""

from __future__ import annotations

import os
from typing import Any
from urllib import error, request

from agent.policies.risk import RiskLevel
from agent.sdk.tool import PluginTool, ToolDefinition


def _http(method: str, path: str, body: dict | None = None) -> dict[str, Any]:
    base = os.environ.get("SMARTOPS_BACKEND_URL", "http://127.0.0.1:8080").rstrip("/")
    url = f"{base}{path}"
    token = os.environ.get("SMARTOPS_AGENT_TOKEN", "")
    import json
    data = json.dumps(body).encode() if body else None
    req = request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode())
        except Exception:
            detail = {"message": e.read().decode(errors="replace")}
        raise RuntimeError(f"HTTP {e.code}: {detail}") from e


class RobotTaskSubmitTool(PluginTool):

    definition = ToolDefinition(
        name="robot.task_submit",
        description="提交设备自主巡检任务。参数：deviceKey（必填）、route（可选，空则后端用默认环形）、planId（可选）。",
        risk=RiskLevel.HIGH,  # HIGH 因为直接驱动物理设备；approval_required 在 manifest 里声明
    )

    async def execute(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        device = str(arguments.get("deviceKey") or "").strip()
        if not device:
            raise ValueError("deviceKey 必填")
        route = arguments.get("route")
        plan_id = arguments.get("planId")
        body = {"route": route, "planId": plan_id} if route is not None else {"planId": plan_id}
        result = _http("POST", f"/api/robot/devices/{device}/tasks", body)
        return {
            "success": result.get("code") == 200,
            "operation": self.definition.name,
            "data": result.get("data"),
            "message": result.get("message"),
        }

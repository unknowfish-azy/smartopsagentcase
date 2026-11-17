"""提交多机队巡检计划（M4）。"""

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


class RobotFleetSubmitTool(PluginTool):

    definition = ToolDefinition(
        name="robot.fleet_submit",
        description=(
            "提交多机队巡检计划。参数：deviceKeys（必填，至少 2 台的列表）、"
            "planId（可选，空则自动生成 PLAN-yyyyMMdd-HHmmss-XXXXXX）。"
            "返回 planId、acceptedCount、rejectedCount 与每台设备的受理明细。"
        ),
        risk=RiskLevel.HIGH,
    )

    async def execute(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        device_keys = arguments.get("deviceKeys") or arguments.get("device_keys")
        if not isinstance(device_keys, list) or len(device_keys) < 2:
            raise ValueError("deviceKeys 必须是至少包含 2 个 deviceKey 的列表")
        plan_id = arguments.get("planId") or arguments.get("plan_id")
        body: dict[str, Any] = {"deviceKeys": device_keys}
        if plan_id:
            body["planId"] = plan_id
        result = _http("POST", "/api/robot/fleet/submit", body)
        return {
            "success": result.get("code") == 200,
            "operation": self.definition.name,
            "data": result.get("data"),
            "message": result.get("message"),
        }

"""查询多机队全局状态（M4）。"""

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


class RobotFleetStatusTool(PluginTool):

    definition = ToolDefinition(
        name="robot.fleet_status",
        description=(
            "查询全局机队状态。返回并发上限、最近 20 个 plan 的汇总"
            "（RUNNING/PAUSED/DONE/FAILED/CANCELLED 计数）。"
        ),
        risk=RiskLevel.LOW,
    )

    async def execute(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        result = _http("GET", "/api/robot/fleet/status")
        return {
            "success": result.get("code") == 200,
            "operation": self.definition.name,
            "data": result.get("data"),
            "message": result.get("message"),
        }

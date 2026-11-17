"""重规划绕行路径工具 —— 接收异常触发点，调本地 Ollama 生成替换 route 段。

对等后端 OllamaReplan.java 的 Python 侧实现，供 agent DAG planner 链路调用。
Fail-closed：Ollama 不可达/解析失败 → 返回 deterministic 兜底（x+2, y+2）。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from agent.policies.risk import RiskLevel
from agent.sdk.tool import PluginTool, ToolDefinition


def _ollama_generate(prompt: str, model: str, base_url: str, timeout: int = 5000) -> str | None:
    import time
    start = time.monotonic()
    try:
        body = json.dumps({
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1},
        }).encode()
        req = urllib.request.Request(
            f"{base_url.rstrip('/')}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout / 1000) as resp:
            data = json.loads(resp.read().decode())
        print(f"[robot.replan_route] ollama {model} ok ({(time.monotonic() - start) * 1000:.0f}ms)")
        return data.get("response", "")
    except Exception as e:
        print(f"[robot.replan_route] ollama failed: {e}")
        return None


def _extract_json(text: str) -> str | None:
    if not text:
        return None
    open_ = text.find("[")
    close = text.rfind("]")
    if open_ >= 0 and close > open_:
        return text[open_: close + 1].strip()
    return None


def _deterministic_fallback(route: list[dict], idx: int, device_key: str) -> dict:
    """兜底：在当前异常点 (x+2, y+2) 生成绕行点。"""
    cur = route[idx]
    return {
        "x": float(cur.get("x", 0)) + 2.0,
        "y": float(cur.get("y", 0)) + 2.0,
        "theta": cur.get("theta", 0),
        "label": f"绕行-{device_key}-py{int(__import__('time').time() * 1000) % 1000}",
        "actions": ["CAPTURE"],
    }


class RobotReplanRouteTool(PluginTool):

    definition = ToolDefinition(
        name="robot.replan_route",
        description="基于视觉异常生成机器人绕行路径段。参数：route（必填，完整巡检路线）、anomalyIndex（必填，触发异常的路点索引）、deviceKey（可选）、ollamaModel（可选，默认复用后端 vision.model）。返回 [{x,y,theta,label,actions}]，可直接替换 route[anomalyIndex]。",
        risk=RiskLevel.MEDIUM,
    )

    async def execute(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        route = arguments.get("route")
        idx = int(arguments.get("anomalyIndex", -1))
        device_key = str(arguments.get("deviceKey") or "unknown")
        if not route or not isinstance(route, list) or idx < 0 or idx >= len(route):
            raise ValueError(f"route(list) + anomalyIndex(0..{len(route) - 1}) 必填")

        model = str(arguments.get("ollamaModel") or os.environ.get("SMARTOPS_ROBOT_REPLAN_OLLAMA_MODEL", "")).strip()
        base = os.environ.get("SMARTOPS_ROBOT_REPLAN_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        timeout = int(arguments.get("timeoutMs") or os.environ.get("SMARTOPS_ROBOT_REPLAN_OLLAMA_TIMEOUT_MS", "5000"))

        # 没配模型 → 直接兜底
        if not model:
            segment = [_deterministic_fallback(route, idx, device_key)]
            return {"routeSegment": segment, "source": "deterministic", "fallback": True}

        prompt = (
            "你是机器人路径重规划器。以下是完整巡检路线（JSON）和异常路点索引。\n"
            f"当前路点检测到连续视觉异常，生成 1-3 个替换绕行点。\n"
            "输出严格 JSON 数组 [{x,y,theta,label,actions}]，仅 JSON 无解释。\n"
            "约束：x/y 在 -5.0 到 +10.0 之间，避免与当前重合，label 以 planner-绕行- 开头。\n\n"
            f"完整路线：\n{json.dumps(route, ensure_ascii=False, indent=2)}\n"
            f"异常路点索引：{idx} 当前点：{json.dumps(route[idx], ensure_ascii=False)}"
        )

        raw = _ollama_generate(prompt, model, base, timeout)
        if raw is None:
            segment = [_deterministic_fallback(route, idx, device_key)]
            return {"routeSegment": segment, "source": "deterministic-fallback", "fallback": True}

        cleaned = _extract_json(raw)
        try:
            segment = json.loads(cleaned) if cleaned else None
        except Exception:
            segment = None

        if not isinstance(segment, list) or not segment:
            segment = [_deterministic_fallback(route, idx, device_key)]
            return {"routeSegment": segment, "source": "deterministic-fallback", "fallback": True}

        for p in segment:
            if not p.get("label"):
                p["label"] = f"planner-绕行-{device_key}"
            if not p.get("actions"):
                p["actions"] = ["CAPTURE"]

        return {"routeSegment": segment, "source": f"ollama-{model}", "fallback": False}

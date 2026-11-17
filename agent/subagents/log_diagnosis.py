"""日志诊断子智能体：并行取证 → 对照已知故障知识。

预置 DAG（两波）：
* 第一波（并行）：容器日志、Nginx 错误日志、目标服务运行状态；
* 第二波：按故障现象检索知识库，对照已知故障模式。

所有工具均为只读（LOW），不触发任何写操作。
"""

from __future__ import annotations

import re

from agent.planner.steps import PlanStep

from .base import SubAgent, SubAgentSpec

SERVICE_RE = re.compile(r"(nginx|mysql|redis)", re.IGNORECASE)
CONTAINER_RE = re.compile(
    r"(?:容器|container)\s*[:：]?\s*([A-Za-z0-9][\w.-]*)",
    re.IGNORECASE,
)

# deploy/docker/docker-compose.yml 里的真实容器名
DEFAULT_CONTAINER = "smartops-backend"

# 目标服务 → 真实状态查询工具（不使用 server.status：当前返回 mock 数据）
SERVICE_STATUS_TOOLS = {
    "nginx": ("nginx.status", {}),
    "mysql": ("mysql.status", {}),
    "redis": ("redis.info", {"section": "memory"}),
}


class LogDiagnosisAgent(SubAgent):
    """日志诊断：先取证，再用知识库里的已知故障模式做对照。"""

    spec = SubAgentSpec(
        name="log_diagnosis",
        title="日志诊断",
        description=(
            "采集容器日志、Nginx 错误日志与目标服务状态，"
            "再按故障现象检索知识库里的已知故障模式，给出诊断线索"
        ),
        keywords=(
            "日志", "log", "报错", "error", "异常", "诊断", "排查",
            "崩溃", "crash", "502", "500", "traceback",
        ),
        tool_names=("docker.logs", "nginx.logs", "nginx.status", "mysql.status", "redis.info", "knowledge.search"),
    )

    def build_steps(self, goal: str) -> list[PlanStep]:
        service = self._infer_service(goal)
        container = self._infer_container(goal)
        status_tool, status_arguments = SERVICE_STATUS_TOOLS[service]

        return [
            PlanStep(
                step_id=1,
                action="采集容器日志",
                tool_name="docker.logs",
                arguments={"container": container, "tail": 300},
                description=f"读取容器 {container} 最近 300 行日志",
            ),
            PlanStep(
                step_id=2,
                action="采集 Nginx 错误日志",
                tool_name="nginx.logs",
                arguments={"tail": 300},
                description="读取 Nginx 错误日志最近 300 行",
            ),
            PlanStep(
                step_id=3,
                action=f"检查 {service} 运行状态",
                tool_name=status_tool,
                arguments=dict(status_arguments),
                description=f"确认 {service} 当前的运行状态",
            ),
            PlanStep(
                step_id=4,
                action="检索已知故障处置知识",
                tool_name="knowledge.search",
                arguments={"query": goal, "top_k": 5},
                description="按故障现象检索知识库，对照已知故障模式",
                depends_on=[1, 2, 3],
            ),
        ]

    @staticmethod
    def _infer_service(goal: str) -> str:
        match = SERVICE_RE.search(goal or "")
        return match.group(1).lower() if match else "nginx"

    @staticmethod
    def _infer_container(goal: str) -> str:
        match = CONTAINER_RE.search(goal or "")
        return match.group(1) if match else DEFAULT_CONTAINER


__all__ = ["LogDiagnosisAgent", "DEFAULT_CONTAINER"]

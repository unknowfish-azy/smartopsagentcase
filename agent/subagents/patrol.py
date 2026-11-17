"""巡检子智能体：一组固定的只读健康检查项，全并行采集。

不使用 server.status（当前返回 mock 数据），全部使用真实只读工具；
所有步骤无依赖、无审批，由 DagExecutor 按波次并行执行。
"""

from __future__ import annotations

from agent.planner.steps import PlanStep

from .base import SubAgent, SubAgentSpec

PATROL_CHECKS: tuple[tuple[str, str, dict, str], ...] = (
    ("nginx.status", "检查 Nginx 服务状态", {}, "确认 Nginx 进程是否处于 active"),
    ("nginx.config_test", "检查 Nginx 配置", {}, "执行 nginx -t 校验配置语法"),
    ("mysql.status", "检查 MySQL 服务状态", {}, "通过 mysqladmin ping 确认可连通"),
    ("redis.info", "检查 Redis 内存指标", {"section": "memory"}, "读取 Redis INFO memory 关键指标"),
    ("redis.memory", "检查 Redis 内存使用", {}, "读取 used_memory / 碎片率等内存摘要"),
    ("docker.ps", "检查容器列表", {}, "确认各容器运行状态与镜像"),
)


class PatrolAgent(SubAgent):
    """巡检：只读健康检查，产出一波并行的检查清单。"""

    spec = SubAgentSpec(
        name="patrol",
        title="巡检",
        description=(
            "对 Nginx / MySQL / Redis 与容器做只读健康巡检，"
            "汇总服务状态、配置自检与资源指标"
        ),
        keywords=(
            "巡检", "体检", "健康检查", "全面检查", "例行检查",
            "整体状态", "状态汇总", "patrol", "health check",
            "所有服务", "全部服务",
        ),
        tool_names=tuple(tool_name for tool_name, _, _, _ in PATROL_CHECKS),
    )

    def build_steps(self, goal: str) -> list[PlanStep]:
        return [
            PlanStep(
                step_id=index,
                action=action,
                tool_name=tool_name,
                arguments=dict(arguments),
                description=description,
            )
            for index, (tool_name, action, arguments, description) in enumerate(
                PATROL_CHECKS, start=1
            )
        ]


__all__ = ["PatrolAgent", "PATROL_CHECKS"]

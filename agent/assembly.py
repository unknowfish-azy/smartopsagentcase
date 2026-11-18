"""Agent 执行链组合根（composition root）。

把"安全基线 bundle + 工具注册中心 + 策略引擎 + 执行器 + 机器人插件"在
一处装配成 AgentAssembly，供未来的应用层入口（调度服务/CLI/HTTP 适配层）
一行取用：

    assembly = build_agent_assembly()
    result = assembly.executor.execute(step, context)

设计约束：
* 依赖方向单向：assembly → executor / policies / tools / security_baseline
  / robot plugin；被装配的任何模块都不反向 import assembly，避免环依赖；
* 纯增量模块，不修改任何既有模块的默认构造行为——执行器与 RobotPlugin
  的可选注入参数保持 None 时语义逐字节不变；
* 安全基线默认开启（生产 fail-closed 语义），security_enabled=False 是
  显式逃生口，关闭后 executor.security_engine is None、robot 守卫为 None；
* 基线装配期哈希链/清单校验失败时 build_security_baseline 直接抛
  ValueError，组合根不吞异常——禁止"无审计裸奔"启动；
* RobotPlugin 属于 kernel 插件生态（agent.registry 那套注册中心），与
  执行器的 agent.tools.registry.ToolRegistry 不是同一套体系，因此这里
  只产出插件实例交给调用方 mount，不做跨体系自动注册。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from agent.executor.dag_executor import DagExecutor
from agent.executor.executor import AgentExecutor, ExecutionPolicy
from agent.plugins.installed.robot.plugin import RobotPlugin
from agent.policies.policy_engine import PolicyEngine
from agent.security_baseline import (
    DEFAULT_AUDIT_DIR,
    SecurityBaselineBundle,
    build_security_baseline,
)
from agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentAssembly:
    """一次装配产出的执行链组合，部件接线在工厂内闭合。"""

    executor: AgentExecutor
    tool_registry: ToolRegistry
    policy_engine: PolicyEngine
    baseline: SecurityBaselineBundle | None
    robot_plugin: RobotPlugin

    def verify_audit_chain(self) -> dict[str, Any] | None:
        """审计链巡检委托；基线关闭时返回 None（无链可验）。"""
        if self.baseline is None:
            return None
        return self.baseline.verify_audit_chain()


def build_agent_assembly(
    *,
    audit_dir: str | Path = DEFAULT_AUDIT_DIR,
    config_path: str | Path | None = None,
    dag: bool = False,
    execution_policy: ExecutionPolicy | None = None,
    security_enabled: bool = True,
    with_robot_guard: bool = True,
    tools: Iterable[Any] = (),
    clock=None,
) -> AgentAssembly:
    """装配生产可用的 Agent 执行链组合。

    参数：
        audit_dir: 审计落盘目录（仅 security_enabled=True 时使用），
            默认 data/security_audit（/data/ 已在 .gitignore 忽略）。
        config_path: 可选外部基线 YAML；None 时用包内 baseline.yaml
            与内置 DEFAULT_BASELINE 深度合并。
        dag: True 时返回 DagExecutor（Kahn 分波调度），否则 AgentExecutor。
        execution_policy: 可选执行闭环参数（重试/超时/死循环阈值）。
        security_enabled: 安全基线总开关，默认 True（fail-closed）；
            False 时执行器不挂引擎、机器人不挂守卫，完全回到历史行为。
        with_robot_guard: 是否给 RobotPlugin 注入 RobotActionGuard；
            security_enabled=False 时该参数无效（守卫必然为 None）。
        tools: 预注册到执行器 ToolRegistry 的工具序列，重名会抛 ValueError。
        clock: 可选时钟注入，主要供固定时钟测试使用。

    抛出：
        ValueError: 工具重名、审计参数非法，或既有审计历史哈希链/清单
            校验失败——后者意味着审计存储可能被篡改，引导必须 fail-closed。
    """
    tool_registry = ToolRegistry()
    for tool in tools:
        tool_registry.register(tool)

    policy_engine = PolicyEngine()

    if security_enabled:
        # build_security_baseline 内部完成 sink 恢复校验，失败即抛，不吞异常。
        bundle = build_security_baseline(
            audit_dir=audit_dir,
            config_path=config_path,
            with_robot_guard=with_robot_guard,
            clock=clock,
        )
        security_engine = bundle.engine
        robot_plugin = RobotPlugin(guard=bundle.robot_guard)
        logger.info(
            "agent_assembly.built mode=%s security=enabled robot_guard=%s audit_dir=%s",
            "dag" if dag else "linear",
            with_robot_guard,
            audit_dir,
        )
    else:
        bundle = None
        security_engine = None
        robot_plugin = RobotPlugin()
        logger.info(
            "agent_assembly.built mode=%s security=disabled (legacy behavior)",
            "dag" if dag else "linear",
        )

    executor_cls = DagExecutor if dag else AgentExecutor
    executor = executor_cls(
        tool_registry,
        policy_engine,
        execution_policy=execution_policy,
        security_engine=security_engine,
    )

    return AgentAssembly(
        executor=executor,
        tool_registry=tool_registry,
        policy_engine=policy_engine,
        baseline=bundle,
        robot_plugin=robot_plugin,
    )


__all__ = ["AgentAssembly", "build_agent_assembly"]

"""ReAct 智能体组合根（P2 阶段 0 + 阶段 1 接线）。

把「大模型 Provider（env 接入）+ 神经网络感知工具（/api/nn/*）+ 执行闭环（含安全基线）」
在一处装配成可直接运行的 ReActPlanner：

    from agent.planner.react_agent import build_react_planner
    from agent.executor.models import ExecutionContext

    planner = build_react_planner()          # provider 默认从 env 建，感知工具默认注册
    result = planner.run("排查 redis 抖动", ExecutionContext("r", "u"))
    print(result.final_answer)

依赖方向单向：react_agent → providers / tools / executor / planner，不反向依赖。
所有部件都可注入覆盖（测试用 fake provider / fake http），默认零配置时：
provider=mock（安全兜底）、感知工具指向 SMARTOPS_AI_SERVICE_URL。
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Iterable

from agent.executor.executor import AgentExecutor, ExecutionPolicy
from agent.policies.policy_engine import PolicyEngine
from agent.providers.model.factory import build_model_provider_from_env
from agent.sdk.model import ModelProvider
from agent.security_baseline import (
    DEFAULT_AUDIT_DIR,
    SecurityBaselineBundle,
    build_security_baseline,
)
from agent.tools.builtin.nn_perception import build_nn_perception_tools
from agent.tools.registry import ToolRegistry

from .react_planner import ReActPlanner

# 进程内按审计目录复用同一份基线 bundle：
# 多个组合根重复装配会各自持有 sink 并写同一条哈希链，容易把链写乱。
_DEFAULT_BASELINE_LOCK = threading.Lock()
_DEFAULT_BASELINES: dict[str, SecurityBaselineBundle] = {}


def _default_baseline(
    audit_dir: str | Path | None,
    config_path: str | Path | None,
) -> SecurityBaselineBundle:
    key = f"{Path(audit_dir or DEFAULT_AUDIT_DIR).resolve()}|{config_path or ''}"
    with _DEFAULT_BASELINE_LOCK:
        bundle = _DEFAULT_BASELINES.get(key)
        if bundle is None:
            bundle = build_security_baseline(
                audit_dir=audit_dir or DEFAULT_AUDIT_DIR,
                config_path=config_path,
            )
            _DEFAULT_BASELINES[key] = bundle
        return bundle


def build_react_planner(
    *,
    provider: ModelProvider | None = None,
    tool_registry: ToolRegistry | None = None,
    executor: AgentExecutor | None = None,
    extra_tools: Iterable[Any] = (),
    ai_service_url: str | None = None,
    perception_http_post=None,
    execution_policy: ExecutionPolicy | None = None,
    max_iterations: int = 8,
    llm_timeout_seconds: float = 30.0,
    security_enabled: bool = True,
    security_engine=None,
    audit_dir: str | Path | None = None,
    baseline_config_path: str | Path | None = None,
) -> ReActPlanner:
    """装配一个可直接运行的 ReActPlanner。

    参数（全部可选，注入即覆盖默认）：
        provider: 大模型 Provider；None 时按 env（LLM_PROVIDER 等）创建，默认 mock。
        tool_registry: 自定义工具中心；None 时新建并注册感知工具 + extra_tools。
        executor: 自定义执行器；None 时用 tool_registry 新建（含策略引擎）。
        extra_tools: 除感知工具外额外注册的工具（如 server/shell 等只读检查工具）。
        ai_service_url: ai-service 地址，默认读 SMARTOPS_AI_SERVICE_URL。
        perception_http_post: 感知工具 HTTP 客户端注入（测试用 fake）。
        execution_policy: 执行闭环参数（重试/超时）。
        max_iterations: ReAct 最大轮次。
        llm_timeout_seconds: 单次 LLM 调用超时。
        security_enabled: 是否给执行器挂安全基线，默认 True（fail-closed）；
            False 是显式逃生口，执行链回到历史行为。
        security_engine: 可注入的基线引擎；不传但 security_enabled=True 时
            按审计目录复用进程级 bundle（L0 合规 / L2 红线 / L1 限流生效）。
        audit_dir: 审计落盘目录，默认 data/security_audit。
        baseline_config_path: 可选外部基线 YAML。
    """
    if provider is None:
        provider = build_model_provider_from_env()

    if tool_registry is None:
        tool_registry = ToolRegistry()
        for tool in build_nn_perception_tools(
            base_url=ai_service_url, http_post=perception_http_post
        ):
            tool_registry.register(tool)
        for tool in extra_tools:
            tool_registry.register(tool)

    if executor is None:
        engine = security_engine
        if engine is None and security_enabled:
            # 默认挂基线：ReAct 路径不能再绕过 L0/L1/L2。
            engine = _default_baseline(audit_dir, baseline_config_path).engine
        executor = AgentExecutor(
            tool_registry,
            PolicyEngine(),
            execution_policy=execution_policy or ExecutionPolicy(),
            security_engine=engine,
        )
    elif security_engine is not None:
        # 注入执行器时只接受显式引擎，避免悄悄改变调用方已装配的行为。
        executor.security_engine = security_engine

    return ReActPlanner(
        provider,
        tool_registry,
        executor,
        max_iterations=max_iterations,
        llm_timeout_seconds=llm_timeout_seconds,
    )


__all__ = ["build_react_planner"]

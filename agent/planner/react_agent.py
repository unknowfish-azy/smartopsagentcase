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

from typing import Any, Iterable

from agent.executor.executor import AgentExecutor, ExecutionPolicy
from agent.policies.policy_engine import PolicyEngine
from agent.providers.model.factory import build_model_provider_from_env
from agent.sdk.model import ModelProvider
from agent.tools.builtin.nn_perception import build_nn_perception_tools
from agent.tools.registry import ToolRegistry

from .react_planner import ReActPlanner


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
        executor = AgentExecutor(
            tool_registry,
            PolicyEngine(),
            execution_policy=execution_policy or ExecutionPolicy(),
        )

    return ReActPlanner(
        provider,
        tool_registry,
        executor,
        max_iterations=max_iterations,
        llm_timeout_seconds=llm_timeout_seconds,
    )


__all__ = ["build_react_planner"]

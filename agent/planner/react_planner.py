"""ReAct Planner（Reasoning + Acting，P2 决策层升级）。

与 LLMPlanner（Plan-and-Execute，一次性出完整计划）不同，ReAct 是**执行式**智能体：
在「Thought → Action → Observation → Thought …」循环里边执行边观察边修正，
每一步都把工具的真实返回（Observation）喂回模型，让它基于新证据决定下一步。

设计要点：
* 复用现有执行闭环：Action 不直接调工具，而是走 AgentExecutor.execute，
  因此参数校验、单步超时、重试退避、安全基线、审计全部继承，不另起炉灶。
* 安全红线：高危工具（requires_approval，HIGH/CRITICAL）不在自主循环里直接执行——
  命中即暂停循环、返回 needs_approval 状态与当前轨迹，交人工/审批流接管。
* 感知工具（/api/nn/* 已注册进 tool_registry 时）作为普通只读工具被模型主动调用，
  输出结构化证据（异常分 / 根因候选 / 日志分类），模型读证据再做研判，决策权在 Agent。
* 失败兜底：模型不可用 / 输出不可解析 / 幻觉工具名，整体降级到规则 Planner，
  与 LLMPlanner 的兜底策略一致，保证链路永远有产出。

输出不是 AgentPlan（那是静态计划），而是 ReActResult：最终结论 + 完整执行轨迹；
同时把已执行步骤折算成 AgentPlan 挂在 result.plan 上，兼容下游按计划消费的场景。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from typing import Any

from agent.executor.executor import AgentExecutor
from agent.executor.models import ExecutionContext
from agent.sdk.model import ModelProvider

from .llm_planner import extract_json_payload
from .models import AgentPlan
from .planner import AgentPlanner
from .steps import PlanStep

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

REACT_SYSTEM_PROMPT = """你是智能运维诊断 Agent，用 ReAct 方式一步步排查问题并给出根因研判。

每一轮你必须严格按以下格式输出（不要输出任何额外解释或 markdown 代码块）：

如果还需要调用工具获取证据：
Thought: 你对当前情况的分析，以及下一步想验证什么
Action: 工具名（只能是工具目录里列出的）
Action Input: 该工具的参数，JSON 对象

如果你已经有足够证据得出结论：
Final Answer: 根因研判结论与处置建议

规则：
1. 一次只调用一个工具，拿到 Observation 后再决定下一步。
2. 感知类工具（异常检测 / 根因打分 / 日志分类）只提供客观证据，根因结论由你综合研判。
3. 优先用只读的检查/感知工具收集证据；高危变更工具不要在自主循环里调用。
4. 证据充分就尽快给出 Final Answer，不要做无意义的重复探测。

可用工具目录：
{catalog}
"""

CATALOG_ITEM_PROMPT = "- {name}: {description}（风险 {risk}，input_schema: {schema}）"

# Action 块解析：Action: <tool>\nAction Input: <json>
_ACTION_RE = re.compile(
    r"Action:\s*(?P<tool>[^\n]+?)\s*\n\s*Action Input:\s*(?P<input>.+)",
    re.DOTALL,
)
_FINAL_RE = re.compile(r"Final Answer:\s*(?P<answer>.+)", re.DOTALL)
_THOUGHT_RE = re.compile(r"Thought:\s*(?P<thought>[^\n]+)")
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_MARKDOWN_LABEL_RE = re.compile(r"\*\*(Thought|Action Input|Action|Final Answer)\*\*")


# ---------------------------------------------------------------------------
# 结果结构
# ---------------------------------------------------------------------------


@dataclass
class ReActStep:
    """单轮 ReAct 轨迹。"""

    iteration: int
    thought: str = ""
    action: str = ""  # 工具名；给出 Final Answer 时为空
    action_input: dict[str, Any] = field(default_factory=dict)
    observation: str = ""  # 工具返回（已截断）
    success: bool | None = None  # 工具执行是否成功；Final Answer 轮为 None

    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "thought": self.thought,
            "action": self.action,
            "action_input": self.action_input,
            "observation": self.observation,
            "success": self.success,
        }


@dataclass
class ReActResult:
    """ReAct 执行结果。"""

    status: str  # completed / needs_approval / max_iterations / failed / rule-fallback
    final_answer: str = ""
    trajectory: list[ReActStep] = field(default_factory=list)
    # 已执行步骤折算成的计划，兼容下游按 AgentPlan 消费；fallback 时是规则计划
    plan: AgentPlan | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.status == "completed" and bool(self.final_answer)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "final_answer": self.final_answer,
            "iterations": len(self.trajectory),
            "trajectory": [s.to_dict() for s in self.trajectory],
            "planner": self.plan.planner if self.plan else None,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# ReAct Planner
# ---------------------------------------------------------------------------


class ReActPlanner:
    """执行式 ReAct 智能体，失败降级规则 Planner。"""

    def __init__(
        self,
        model_provider: ModelProvider,
        tool_registry,
        executor: AgentExecutor,
        fallback_planner: AgentPlanner | None = None,
        max_iterations: int = 8,
        llm_timeout_seconds: float = 30.0,
        observation_budget: int = 2000,
    ) -> None:
        self.model_provider = model_provider
        self.tool_registry = tool_registry
        self.executor = executor
        self.fallback_planner = fallback_planner or AgentPlanner()
        self.max_iterations = max_iterations
        self.llm_timeout_seconds = llm_timeout_seconds
        # 单次 Observation 喂回模型的字符预算，避免大输出爆上下文（小模型尤其敏感）
        self.observation_budget = observation_budget

    # ------------------------------------------------------------------
    # 对外入口
    # ------------------------------------------------------------------

    def run(
        self,
        goal: str,
        context: ExecutionContext,
        failure_context: str | None = None,
    ) -> ReActResult:
        """驱动 ReAct 循环直到 Final Answer / 审批暂停 / 达到轮次上限 / 降级。"""

        catalog = self._build_catalog()
        history = ""  # 累积的「Thought/Action/Observation」文本轨迹
        trajectory: list[ReActStep] = []
        executed_steps: list[PlanStep] = []

        if failure_context:
            history += f"上一次失败上下文（避免重复失败路径）：{failure_context}\n"

        try:
            for iteration in range(1, self.max_iterations + 1):
                prompt = self._build_prompt(catalog, goal, history)
                response_text = self._normalize_response(self._call_model(prompt))

                # 1) Final Answer：证据充分，收尾
                final = _FINAL_RE.search(response_text)
                if final:
                    trajectory.append(
                        ReActStep(
                            iteration=iteration,
                            thought=self._extract_thought(response_text),
                            observation=final.group("answer").strip(),
                        )
                    )
                    return self._finish(
                        "completed",
                        final_answer=final.group("answer").strip(),
                        trajectory=trajectory,
                        executed_steps=executed_steps,
                        goal=goal,
                    )

                # 2) Action：解析工具调用
                action_match = _ACTION_RE.search(response_text)
                if not action_match:
                    # 既不是 Final Answer 也不是合法 Action：小模型常见，给一次纠错机会
                    logger.warning("react unparsable output at iter %s", iteration)
                    history += (
                        f"你的上一次输出无法解析，请严格按格式输出 Thought/Action/Action Input "
                        f"或 Final Answer。你的原输出：{response_text[:300]}\n"
                    )
                    continue

                tool_name = action_match.group("tool").strip()
                raw_input = action_match.group("input").strip()
                thought = self._extract_thought(response_text)

                tool = self.tool_registry.get(tool_name)
                if tool is None:
                    # 幻觉工具名：不降级整个链路，把错误作为 Observation 喂回让它自我纠正
                    observation = f"错误：工具 '{tool_name}' 不存在，请从工具目录中选择。"
                    trajectory.append(
                        ReActStep(
                            iteration=iteration,
                            thought=thought,
                            action=tool_name,
                            observation=observation,
                            success=False,
                        )
                    )
                    history += self._format_step(thought, tool_name, raw_input, observation)
                    continue

                arguments = self._parse_arguments(raw_input)

                # 3) 安全红线：高危工具暂停自主循环，交审批
                if bool(getattr(tool, "requires_approval", False)) and not context.dry_run:
                    step = PlanStep(
                        step_id=len(executed_steps) + 1,
                        action=thought or tool_name,
                        tool_name=tool_name,
                        arguments=arguments,
                        description=thought,
                        requires_approval=True,
                    )
                    executed_steps.append(step)
                    trajectory.append(
                        ReActStep(
                            iteration=iteration,
                            thought=thought,
                            action=tool_name,
                            action_input=arguments,
                            observation="该操作为高危变更，已暂停自主执行，等待人工审批。",
                        )
                    )
                    logger.info("react needs_approval tool=%s iter=%s", tool_name, iteration)
                    return self._finish(
                        "needs_approval",
                        trajectory=trajectory,
                        executed_steps=executed_steps,
                        goal=goal,
                        metadata={"pending_tool": tool_name, "pending_arguments": arguments},
                    )

                # 4) 执行工具（复用执行闭环），拿 Observation
                step = PlanStep(
                    step_id=len(executed_steps) + 1,
                    action=thought or tool_name,
                    tool_name=tool_name,
                    arguments=arguments,
                    description=thought,
                )
                result = self.executor.execute(step, context)
                executed_steps.append(step)
                observation = self._format_observation(result)

                trajectory.append(
                    ReActStep(
                        iteration=iteration,
                        thought=thought,
                        action=tool_name,
                        action_input=arguments,
                        observation=observation,
                        success=result.success,
                    )
                )
                history += self._format_step(thought, tool_name, raw_input, observation)

            # 轮次耗尽：把已有轨迹整理返回，标记未得出结论
            logger.info("react max_iterations=%s reached", self.max_iterations)
            return self._finish(
                "max_iterations",
                trajectory=trajectory,
                executed_steps=executed_steps,
                goal=goal,
                metadata={"reason": f"达到最大轮次 {self.max_iterations}，未给出 Final Answer"},
            )

        except Exception as exc:  # noqa: BLE001 - 决策链路不允许因 LLM 故障而中断
            reason = f"{type(exc).__name__}: {exc}"
            logger.warning("react failed -> fallback to rule planner: %s", reason)
            fallback = self.fallback_planner.create_plan(goal)
            fallback.planner = "rule-fallback"
            fallback.metadata = {"fallback_reason": reason}
            return ReActResult(
                status="rule-fallback",
                trajectory=trajectory,
                plan=fallback,
                metadata={"fallback_reason": reason},
            )

    # 与 AgentPlanner.create_plan 兼容的别名，便于上层统一按规划器调用
    def create_plan(self, goal: str, context: ExecutionContext) -> AgentPlan | ReActResult:
        return self.run(goal, context)

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _build_catalog(self) -> str:
        items = []
        for tool in self.tool_registry.list_tools():
            definition = getattr(tool, "definition", None)
            risk = getattr(definition, "risk", getattr(tool, "risk_level", "LOW"))
            schema = getattr(definition, "input_schema", None) or {}
            items.append(
                CATALOG_ITEM_PROMPT.format(
                    name=tool.name,
                    description=getattr(tool, "description", ""),
                    risk=risk,
                    schema=json.dumps(schema, ensure_ascii=False),
                )
            )
        return "\n".join(items) or "（无工具）"

    def _build_prompt(self, catalog: str, goal: str, history: str) -> str:
        sections = [
            REACT_SYSTEM_PROMPT.format(catalog=catalog),
            f"目标：{goal}",
        ]
        if history:
            sections.append(f"已执行的排查过程（Thought/Action/Observation 轨迹）：\n{history}")
        sections.append("请输出下一轮（Thought/Action/Action Input 或 Final Answer）：")
        return "\n\n".join(sections)

    def _call_model(self, prompt: str) -> str:
        """同步上下文调用异步模型 Provider，带独立超时（与 LLMPlanner 同策略）。"""

        coroutine = self.model_provider.generate(prompt)
        timeout = self.llm_timeout_seconds

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coroutine)
                try:
                    response = future.result(timeout=timeout)
                except FutureTimeoutError:
                    future.cancel()
                    raise TimeoutError(f"ReAct LLM 调用超时（{timeout}s）") from None
        else:
            with ThreadPoolExecutor(max_workers=1) as pool:
                response = pool.submit(asyncio.run, coroutine).result()

        return response.content

    @staticmethod
    def _normalize_response(text: str) -> str:
        """剥离推理模型的思考块，并兼容 Markdown 加粗的 ReAct 标签。"""
        text = _THINK_BLOCK_RE.sub("", text)
        text = re.sub(r"</think>", "", text, flags=re.IGNORECASE)
        return _MARKDOWN_LABEL_RE.sub(r"\1", text)

    @staticmethod
    def _extract_thought(text: str) -> str:
        match = _THOUGHT_RE.search(text)
        return match.group("thought").strip() if match else ""

    @staticmethod
    def _parse_arguments(raw_input: str) -> dict[str, Any]:
        """Action Input 解析为参数对象；容忍代码围栏，非法则回退空对象。"""
        payload = extract_json_payload(raw_input)
        if isinstance(payload, dict):
            return payload
        return {}

    def _format_observation(self, result) -> str:
        """把 ExecutionResult 转成喂回模型的 Observation 文本，按预算截断。"""
        if result.success:
            body = result.output if result.output is not None else result.message
        else:
            body = f"执行失败：{result.error or result.message}"
            if result.error_category:
                body += f"（错误类别 {result.error_category}）"
        text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, default=str)
        if len(text) > self.observation_budget:
            text = text[: self.observation_budget] + "…（输出过长已截断）"
        return text

    @staticmethod
    def _format_step(thought: str, tool_name: str, raw_input: str, observation: str) -> str:
        return (
            f"Thought: {thought}\n"
            f"Action: {tool_name}\n"
            f"Action Input: {raw_input}\n"
            f"Observation: {observation}\n"
        )

    def _finish(
        self,
        status: str,
        trajectory: list[ReActStep],
        executed_steps: list[PlanStep],
        goal: str,
        final_answer: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ReActResult:
        plan = AgentPlan(
            request_id=goal[:32],
            goal=goal,
            steps=executed_steps,
            requires_human_approval=any(s.requires_approval for s in executed_steps),
            planner="react",
            metadata=dict(metadata or {}),
        )
        return ReActResult(
            status=status,
            final_answer=final_answer,
            trajectory=trajectory,
            plan=plan,
            metadata=dict(metadata or {}),
        )


__all__ = [
    "ReActPlanner",
    "ReActResult",
    "ReActStep",
    "REACT_SYSTEM_PROMPT",
]

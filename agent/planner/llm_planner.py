"""LLM Planner（Plan-and-Execute，P1）。

用大模型把目标拆解为多步计划（先整体规划再执行），
输出强制 JSON 并做严格校验（工具必须存在、参数必须是对象）；
任何一步出错（模型不可用 / 输出非法 JSON / 规划了不存在的工具）
都自动降级到规则 Planner，保证规划链路永远有产出。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError

from agent.sdk.model import ModelProvider

from .dag import repair_dag, validate_dag
from .models import AgentPlan
from .planner import AgentPlanner
from .steps import PlanStep

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """你是智能运维规划器。根据目标和可用工具目录，输出一个 JSON 执行计划。

要求：
1. 只输出 JSON，不要输出任何解释文字或 markdown 代码块。
2. 优先"检查/验证"，再"执行修改"，最后一步必须是验证步骤。
3. 只能使用工具目录里列出的工具，参数必须符合该工具的 input_schema。
4. 高风险操作（HIGH/CRITICAL）必须把 requires_approval 设为 true。
5. 步骤数量不超过 {max_steps}。
6. 步骤间可并行时，用 depends_on 声明依赖（前置步骤的 step_id 数组）；无依赖则留空数组。
   step_id 从 1 开始按顺序编号，禁止依赖不存在的步骤，禁止循环依赖。

输出格式：
{{"steps": [{{"step_id": 1, "action": "动作名", "tool_name": "工具名", "arguments": {{}}, "description": "步骤说明", "requires_approval": false, "depends_on": []}}]}}"""

CATALOG_ITEM_PROMPT = "- {name}: {description}（风险 {risk}，input_schema: {schema}）"


def extract_json_payload(text: str) -> dict | None:
    """从模型输出中稳健地提取 JSON 对象（容忍代码围栏与前后杂质）。"""

    if not text:
        return None

    cleaned = re.sub(r"```(?:json)?", "", text).strip()

    for candidate in (cleaned, text.strip()):
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            continue

    # 前后杂质：截取第一个 { 到最后一个 }
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            return None
    return None


class LLMPlanner:
    """LLM 规划器，失败自动降级到规则 Planner。"""

    def __init__(
        self,
        model_provider: ModelProvider,
        tool_registry,
        fallback_planner: AgentPlanner | None = None,
        max_steps: int = 8,
        llm_timeout_seconds: float = 30.0,
    ) -> None:
        self.model_provider = model_provider
        self.tool_registry = tool_registry
        self.fallback_planner = fallback_planner or AgentPlanner()
        self.max_steps = max_steps
        self.llm_timeout_seconds = llm_timeout_seconds

    # ------------------------------------------------------------------
    # 对外入口（与 AgentPlanner.create_plan 签名兼容）
    # ------------------------------------------------------------------

    def create_plan(
        self,
        goal: str,
        failure_context: str | None = None,
    ) -> AgentPlan:
        """生成计划；LLM 失败时降级规则 Planner（plan.planner 标注来源）。"""

        prompt = self._build_prompt(goal, failure_context)
        try:
            response_text = self._call_model(prompt)
            plan = self._parse_plan(response_text, goal)
            if plan is not None:
                plan.planner = "llm"
                logger.info(
                    "planner.llm ok goal=%s steps=%s", goal, len(plan.steps)
                )
                return plan
            reason = "输出为空或缺少合法 steps"
        except Exception as exc:  # noqa: BLE001 - 规划链路不允许因 LLM 故障而中断
            reason = f"{type(exc).__name__}: {exc}"
            logger.warning("planner.llm failed -> fallback to rule planner: %s", reason)

        fallback = self.fallback_planner.create_plan(goal)
        fallback.planner = "rule-fallback"
        fallback.metadata = {"fallback_reason": reason}
        return fallback

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _build_prompt(self, goal: str, failure_context: str | None) -> str:
        catalog_items = []
        for tool in self.tool_registry.list_tools():
            definition = getattr(tool, "definition", None)
            risk = getattr(definition, "risk", getattr(tool, "risk_level", "LOW"))
            schema = getattr(definition, "input_schema", None) or {}
            catalog_items.append(
                CATALOG_ITEM_PROMPT.format(
                    name=tool.name,
                    description=getattr(tool, "description", ""),
                    risk=risk,
                    schema=json.dumps(schema, ensure_ascii=False),
                )
            )

        sections = [
            PLANNER_SYSTEM_PROMPT.format(max_steps=self.max_steps),
            "可用工具目录：",
            "\n".join(catalog_items) or "（无工具）",
            f"目标：{goal}",
        ]
        if failure_context:
            sections.append(f"上一次执行的失败上下文（重规划时参考，避免重复失败路径）：{failure_context}")
        return "\n".join(sections)

    def _call_model(self, prompt: str) -> str:
        """同步上下文调用异步模型 Provider，带独立超时。"""

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
                    raise TimeoutError(f"LLM 规划超时（{timeout}s）") from None
        else:
            with ThreadPoolExecutor(max_workers=1) as pool:
                response = pool.submit(asyncio.run, coroutine).result()

        return response.content

    def _parse_plan(self, text: str, goal: str) -> AgentPlan | None:
        payload = extract_json_payload(text)
        if not payload:
            return None

        raw_steps = payload.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            return None

        steps: list[PlanStep] = []
        for raw in raw_steps[: self.max_steps]:
            if not isinstance(raw, dict):
                return None
            tool_name = str(raw.get("tool_name", "")).strip()
            tool = self.tool_registry.get(tool_name)
            if tool is None:
                # 规划了不存在的工具：整体不可信，走降级
                logger.warning("planner.llm unknown tool %s", tool_name)
                return None
            arguments = raw.get("arguments")
            if not isinstance(arguments, dict):
                arguments = {}
            # 风险控制：不信任模型输出的 requires_approval，高危工具强制审批
            requires_approval = bool(raw.get("requires_approval", False)) or bool(
                getattr(tool, "requires_approval", False)
            )
            depends_on = raw.get("depends_on")
            if not isinstance(depends_on, list):
                depends_on = []
            steps.append(
                PlanStep(
                    step_id=len(steps) + 1,
                    action=str(raw.get("action") or tool_name),
                    tool_name=tool_name,
                    arguments=arguments,
                    description=str(raw.get("description", "")),
                    requires_approval=requires_approval,
                    depends_on=[int(x) for x in depends_on if isinstance(x, (int, float))],
                )
            )

        if not steps:
            return None

        # P3（蒸馏 AgentForge）：DAG 逐条校验 → 修复一次 → 再失败压平线性退回
        metadata: dict = {}
        validation = validate_dag(steps)
        if not validation.ok:
            logger.warning("planner.llm dag invalid: %s -> repair once", validation.problems)
            repaired = repair_dag(steps)
            if repaired is not None:
                steps = repaired
                metadata["dag_repaired"] = validation.problems
            else:
                flattened = [
                    PlanStep(
                        step_id=i + 1,
                        action=s.action,
                        tool_name=s.tool_name,
                        arguments=s.arguments,
                        description=s.description,
                        requires_approval=s.requires_approval,
                        depends_on=[],
                    )
                    for i, s in enumerate(steps)
                ]
                steps = flattened
                metadata["dag_flattened"] = validation.problems

        return AgentPlan(
            request_id=goal[:32],  # 正式 request_id 由 Runner/执行层分配
            goal=goal,
            steps=steps,
            requires_human_approval=any(step.requires_approval for step in steps),
            metadata=metadata,
        )


__all__ = [
    "LLMPlanner",
    "extract_json_payload",
    "PLANNER_SYSTEM_PROMPT",
]

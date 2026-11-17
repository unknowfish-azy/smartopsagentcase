"""反思与自我纠错（P1）。

计划执行失败后，由 Reflector 评审结果并给出裁决：
* pass：全部成功，任务收尾；
* replan：存在失败步骤，携带失败上下文重新规划。

反思次数由调用方（PlanRunner）设上限，防止"无限自检"。
无模型时自动退化为规则裁决（有失败即重规划），链路永不中断。
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from agent.sdk.model import ModelProvider

from agent.planner.llm_planner import extract_json_payload

logger = logging.getLogger(__name__)

REFLECTION_SYSTEM_PROMPT = """你是智能运维评审员。根据任务目标和每一步的执行结果，判断整体执行是否达标。

要求：
1. 只输出 JSON。
2. decision 只能是 "pass"（达标收尾）或 "replan"（存在未解决失败，需要重规划）。
3. failed_step_ids 列出需要处理的失败步骤编号；全部达标时为空数组。

输出格式：
{"decision": "pass", "reason": "简述判断依据", "failed_step_ids": []}"""


@dataclass
class ReflectionVerdict:
    decision: str  # pass / replan
    reason: str = ""
    failed_step_ids: list[int] = field(default_factory=list)
    source: str = "rule"  # rule / llm / llm-fallback


class Reflector:
    """执行结果评审器：LLM 评审优先，失败退化为规则裁决。"""

    def __init__(
        self,
        model_provider: ModelProvider | None = None,
        llm_timeout_seconds: float = 20.0,
    ) -> None:
        self.model_provider = model_provider
        self.llm_timeout_seconds = llm_timeout_seconds

    def review(self, goal: str, plan_result) -> ReflectionVerdict:
        if self.model_provider is not None:
            try:
                verdict = self._review_with_llm(goal, plan_result)
                if verdict is not None:
                    verdict.source = "llm"
                    return verdict
            except Exception as exc:  # noqa: BLE001 - 反思不允许阻塞执行链路
                logger.warning("reflector.llm failed -> rule verdict: %s", exc)
            verdict = self._rule_verdict(plan_result)
            verdict.source = "llm-fallback"
            return verdict
        return self._rule_verdict(plan_result)

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _rule_verdict(self, plan_result) -> ReflectionVerdict:
        failed = [r for r in plan_result.step_results if not r.success]
        if not failed:
            return ReflectionVerdict(
                decision="pass",
                reason=f"全部 {len(plan_result.step_results)} 步执行成功",
            )
        return ReflectionVerdict(
            decision="replan",
            reason=f"{len(failed)} 步失败: " + "; ".join(
                f"步骤{r.metadata.get('step_id')}[{r.tool_name}] {r.error}" for r in failed
            ),
            failed_step_ids=[
                int(r.metadata.get("step_id", 0)) for r in failed
            ],
        )

    def _review_with_llm(self, goal: str, plan_result) -> ReflectionVerdict | None:
        lines = []
        for result in plan_result.step_results:
            lines.append(
                "- 步骤{sid} 工具 {tool}: {status}{err}".format(
                    sid=result.metadata.get("step_id"),
                    tool=result.tool_name,
                    status="成功" if result.success else f"失败 [{result.error_category}]",
                    err=f"（{result.error}）" if not result.success and result.error else "",
                )
            )
        prompt = "\n".join([
            REFLECTION_SYSTEM_PROMPT,
            f"任务目标：{goal}",
            "执行结果：",
            *lines,
            f"整体状态：{plan_result.status}",
        ])

        with ThreadPoolExecutor(max_workers=1) as pool:
            response = pool.submit(
                asyncio.run,
                self.model_provider.generate(prompt),
            ).result(timeout=self.llm_timeout_seconds)

        payload = extract_json_payload(response.content)
        if not payload:
            return None

        decision = str(payload.get("decision", "")).strip().lower()
        if decision not in {"pass", "replan"}:
            return None

        raw_ids = payload.get("failed_step_ids")
        failed_ids = []
        if isinstance(raw_ids, list):
            failed_ids = [int(item) for item in raw_ids if isinstance(item, (int, float))]

        return ReflectionVerdict(
            decision=decision,
            reason=str(payload.get("reason", "")),
            failed_step_ids=failed_ids,
        )


__all__ = [
    "ReflectionVerdict",
    "Reflector",
    "REFLECTION_SYSTEM_PROMPT",
]

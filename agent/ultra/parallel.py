"""Ultra 多路择优（P4，蒸馏 AgentForge 的"一个环节并行多路 + 两层审阅"）。

AgentForge 机制：重要环节同时派出多路 agent（不同取向：严谨/深度落地/全面创新），
先多路择优，再方向校准；批量请求合并、失败单路不影响其他路。

本实现（能力模块，独立于主链路；P3 路由的 L4 已预留）：
* ``UltraRunner.run_stage``  并行 N 路生成（单路失败占位不影响他路）
  → judge 打分择优 → 可选校准包装；
* 取向是**提示词 persona**，不是"多个不同模型"——诚实口径；
* ``generate_fn`` / ``judge_fn`` / ``calibrate_fn`` 全部注入：生产接 LLM，
  测试接 stub；未配置 judge 时按生成序取第一路并明确标注 default_first。

线程模型：ThreadPoolExecutor 并行（生成函数为同步契约），单路异常被捕获
记为 failed 占位，全部失败抛 ``UltraError``。
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


class UltraError(RuntimeError):
    """全部候选路失败，无产出。"""


# 取向 persona：三路默认配置（对齐 AgentForge 的严谨/深度/创新三取向）
ULTRA_PERSONAS: dict[str, str] = {
    "rigorous": "取向：严谨。只给有把握的结论，宁缺毋滥，标注不确定之处。",
    "pragmatic": "取向：深度落地。优先给出可立即执行的步骤与边界条件。",
    "creative": "取向：全面创新。补充常规思路之外的替代方案，并说明权衡。",
}

JudgeFn = Callable[[str, dict[str, str]], dict[str, float]]
CalibrateFn = Callable[[str, str], str]
GenerateFn = Callable[[str, str, str], str]  # (objective, persona_key, persona_prompt) -> output


@dataclass
class UltraResult:
    """多路择优结果：最优产出 + 全量评分证据。"""

    objective: str
    best_persona: str
    best_output: str
    outputs: dict[str, str] = field(default_factory=dict)      # persona -> 产出（失败为 ""）
    failures: dict[str, str] = field(default_factory=dict)     # persona -> 失败原因
    scores: dict[str, float] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)
    judge: str = "default_first"                                # 注入 judge 名 / default_first
    calibrated: bool = False

    @property
    def success(self) -> bool:
        return bool(self.best_output)

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "best_persona": self.best_persona,
            "best_output": self.best_output,
            "outputs": self.outputs,
            "failures": self.failures,
            "scores": self.scores,
            "reasons": self.reasons,
            "judge": self.judge,
            "calibrated": self.calibrated,
        }


class UltraRunner:
    """同一环节并行多路生成 → 择优 → 校准。"""

    def __init__(
        self,
        generate_fn: GenerateFn,
        judge_fn: JudgeFn | None = None,
        calibrate_fn: CalibrateFn | None = None,
        judge_name: str = "injected",
        max_concurrency: int = 3,
    ) -> None:
        self.generate_fn = generate_fn
        self.judge_fn = judge_fn
        self.calibrate_fn = calibrate_fn
        self.judge_name = judge_name
        self.max_concurrency = max(1, max_concurrency)

    def run_stage(self, objective: str, personas: dict[str, str] | None = None) -> UltraResult:
        persona_prompts = personas or ULTRA_PERSONAS
        if not persona_prompts:
            raise UltraError("未提供任何取向 persona")

        # 1) 并行多路生成（单路异常 → failed 占位，不拖垮其他路）
        results: dict[str, str] = {}
        failures: dict[str, str] = {}

        def _generate(persona_key: str) -> tuple[str, str | None, str | None]:
            try:
                output = self.generate_fn(objective, persona_key, persona_prompts[persona_key])
                return persona_key, str(output).strip(), None
            except Exception as exc:  # noqa: BLE001 - 单路失败隔离
                return persona_key, None, f"{type(exc).__name__}: {exc}"

        with ThreadPoolExecutor(max_workers=min(self.max_concurrency, len(persona_prompts))) as pool:
            for persona_key, output, error in pool.map(_generate, persona_prompts):
                if error is None and output:
                    results[persona_key] = output
                else:
                    failures[persona_key] = error or "空产出"

        if not results:
            raise UltraError(f"全部 {len(persona_prompts)} 路候选失败: {failures}")

        # 2) 多路择优
        scores: dict[str, float] = {}
        reasons: dict[str, str] = {}
        if self.judge_fn is not None:
            scores, reasons = self.judge_fn(objective, dict(results))
            best_persona = max(scores, key=lambda key: scores[key])
            judge = self.judge_name
        else:
            best_persona = next(iter(results))  # 无评审器：按生成序取第一路，诚实标注
            scores = {key: 1.0 for key in results}
            judge = "default_first"
            reasons[best_persona] = "未配置评审器，按生成顺序取第一路（非择优）"

        best_output = results[best_persona]
        logger.info(
            "ultra.stage objective=%s personas=%s ok=%s best=%s judge=%s",
            objective[:32], list(persona_prompts), list(results), best_persona, judge,
        )

        # 3) 方向校准（可选，包装最优产出）
        calibrated = False
        if self.calibrate_fn is not None:
            best_output = self.calibrate_fn(objective, best_output).strip()
            calibrated = True

        return UltraResult(
            objective=objective,
            best_persona=best_persona,
            best_output=best_output,
            outputs=results,
            failures=failures,
            scores=scores,
            reasons=reasons,
            judge=judge,
            calibrated=calibrated,
        )


__all__ = ["UltraRunner", "UltraResult", "UltraError", "ULTRA_PERSONAS"]

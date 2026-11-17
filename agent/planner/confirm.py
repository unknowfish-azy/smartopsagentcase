"""执行前确认门（P3，蒸馏 AgentForge 的"计划 + 预算确认后才执行"）。

AgentForge 机制：发送任务前展示计划节点数与 token 预算，确认后才执行。
本实现：
* ``PlanGate.summary``   计划摘要：节点数、工具清单、审批步骤、token 粗估；
* ``PlanGate.confirm``   调用注入的 approver 回调（UI 弹窗 / API 审批）；
  未配置 approver 时默认放行（向后兼容，dry_run/CI 场景不受阻）。

token 估算口径（诚实）：按"每步固定基数 + 参数 JSON 字节数/4"粗估，
用于人工判断规模，不是精确计费数字；对外展示必须标注"估算"。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)

# 粗估参数：每步固定 token 开销（提示词 + 工具描述 + 返回摘要）
_TOKENS_PER_STEP = 800
_TOKENS_PER_PARAM_BYTE = 0.25  # 参数 JSON 每 4 字节约 1 token


@dataclass
class PlanSummary:
    """计划摘要（确认门展示给用户的内容）。"""

    node_count: int
    tool_names: list[str]
    approval_steps: list[int]
    estimated_tokens: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_count": self.node_count,
            "tool_names": self.tool_names,
            "approval_steps": self.approval_steps,
            "estimated_tokens": self.estimated_tokens,
        }


class PlanGate:
    """执行前确认门：摘要 → 人工确认 → 放行/否决。"""

    def __init__(self, approver: Callable[[PlanSummary], bool] | None = None):
        self.approver = approver

    def summarize(self, plan) -> PlanSummary:
        steps = getattr(plan, "steps", [])
        estimated = 0
        for step in steps:
            try:
                param_bytes = len(json.dumps(step.arguments, ensure_ascii=False, default=str))
            except (TypeError, ValueError):
                param_bytes = len(str(step.arguments))
            estimated += _TOKENS_PER_STEP + int(param_bytes * _TOKENS_PER_PARAM_BYTE)
        return PlanSummary(
            node_count=len(steps),
            tool_names=[s.tool_name for s in steps],
            approval_steps=[s.step_id for s in steps if s.requires_approval],
            estimated_tokens=estimated,
        )

    def confirm(self, plan) -> tuple[bool, PlanSummary]:
        """返回 (是否放行, 摘要)。无 approver 时默认放行并记录日志。"""

        summary = self.summarize(plan)
        if self.approver is None:
            logger.info(
                "plan_gate.auto_approve nodes=%s est_tokens=%s（未配置 approver，默认放行）",
                summary.node_count, summary.estimated_tokens,
            )
            return True, summary
        approved = bool(self.approver(summary))
        logger.info(
            "plan_gate.approved=%s nodes=%s est_tokens=%s approval_steps=%s",
            approved, summary.node_count, summary.estimated_tokens, summary.approval_steps,
        )
        return approved, summary


__all__ = ["PlanGate", "PlanSummary"]

"""
AI Judge（Level 3）。

使用 Judge Model 对 Agent 行为进行综合判定。

默认不绑定具体模型，可注入任意 judge 函数（本地/云端模型均可）。
未注入时返回确定性 PASS，保证 Inspector 流程不因缺少模型而中断。
"""

from __future__ import annotations

from typing import Any, Callable

from agent.inspector.enums import InspectionCategory, Severity
from agent.inspector.judges.base import Judge
from agent.inspector.models import InspectorIssue

# judge_fn(context: dict) -> list[InspectorIssue]
JudgeFn = Callable[[dict[str, Any]], list[InspectorIssue]]


class AIJudge(Judge):
    """可插拔的 AI 综合判定器。"""

    def __init__(
        self,
        judge_fn: JudgeFn | None = None,
    ) -> None:
        self.judge_fn = judge_fn

    def check(self, context: dict[str, Any]) -> list[InspectorIssue]:
        if self.judge_fn is None:
            return []

        issues = self.judge_fn(context)

        if not isinstance(issues, list):
            return []

        return [
            issue
            for issue in issues
            if isinstance(issue, InspectorIssue)
        ]

    @staticmethod
    def passthrough() -> list[InspectorIssue]:
        return []


__all__ = [
    "AIJudge",
    "JudgeFn",
]

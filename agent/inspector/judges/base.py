"""
Judge 抽象基类。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from agent.inspector.models import InspectorIssue


class Judge(ABC):
    """纠察判定器统一接口。"""

    @abstractmethod
    def check(
        self,
        context: dict[str, Any],
    ) -> list[InspectorIssue]:
        """对纠察上下文进行检查，返回发现的问题列表。"""
        raise NotImplementedError


__all__ = ["Judge"]

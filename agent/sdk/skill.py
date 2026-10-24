from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Skill:
    """
    SmartOps Skill 模型。

    表示一个可被 Agent 发现、加载、注册和执行的运维技能。
    """

    name: str
    description: str = ""
    version: str = "1.0.0"
    path: str | Path | None = None
    tags: list[str] = field(default_factory=list)
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def matches(self, query: str) -> bool:
        """
        判断该 Skill 是否匹配关键词查询。

        匹配范围：名称、描述、标签。
        """
        query = (query or "").strip().lower()

        if not query:
            return True

        haystack = " ".join(
            [
                self.name,
                self.description,
                *self.tags,
            ]
        ).lower()

        return query in haystack


__all__ = [
    "Skill",
]

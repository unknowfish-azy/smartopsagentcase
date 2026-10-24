from dataclasses import dataclass, field


@dataclass(frozen=True)
class Permission:
    """
    Capability权限模型。

    示例：
    server:status
    filesystem:read
    shell:execute
    """

    resource: str
    actions: frozenset[str] = field(default_factory=frozenset)

    def allows(self, action: str) -> bool:
        return action in self.actions or "*" in self.actions

    @property
    def key(self) -> str:
        if not self.actions:
            return self.resource

        actions = ",".join(sorted(self.actions))
        return f"{self.resource}:{actions}"
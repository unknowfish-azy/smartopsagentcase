from dataclasses import dataclass, field
from typing import Any


@dataclass
class PluginContext:
    plugin_id: str
    request_id: str
    user_id: str | None
    role: str
    permissions: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class AgentEvent:
    name: str
    request_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


PLUGIN_MOUNTED = "plugin.mounted"
PLUGIN_UNMOUNTED = "plugin.unmounted"

SKILL_LOADED = "skill.loaded"
SKILL_UNLOADED = "skill.unloaded"

TOOL_BEFORE_CALL = "tool.before_call"
TOOL_AFTER_CALL = "tool.after_call"

APPROVAL_REQUIRED = "approval.required"
APPROVAL_GRANTED = "approval.granted"
APPROVAL_DENIED = "approval.denied"

EXECUTION_STARTED = "execution.started"
EXECUTION_FINISHED = "execution.finished"

VERIFICATION_STARTED = "verification.started"
VERIFICATION_FINISHED = "verification.finished"

AUDIT_CREATED = "audit.created"
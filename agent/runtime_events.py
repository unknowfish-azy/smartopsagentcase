"""Minimal correlation events. Payloads, credentials and prompts never enter here."""
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from uuid import uuid4

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z")
STATUSES = frozenset({"started", "succeeded", "failed", "denied", "dry_run"})


def safe_id(value):
    return value if isinstance(value, str) and _ID.fullmatch(value) else uuid4().hex


@dataclass(frozen=True)
class RunIdentity:
    request_id: str
    task_id: str
    run_id: str

    @classmethod
    def create(cls, *, request_id=None, task_id=None, run_id=None):
        request = safe_id(request_id)
        return cls(request, safe_id(task_id) if task_id is not None else request, safe_id(run_id))


def terminal_event(identity, source, status, *, step_id=None):
    """Strict allowlist: no arbitrary metadata/exception/output serialization."""
    if status not in STATUSES or source not in {"executor", "ai-service", "backend"}:
        raise ValueError("Unknown event source or status")
    return {
        "schema_version": "1.0.0",
        "event_id": uuid4().hex,
        "request_id": identity.request_id,
        "task_id": identity.task_id,
        "run_id": identity.run_id,
        "step_id": safe_id(str(step_id)) if step_id is not None else None,
        "source": source,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

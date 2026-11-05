"""Correlation IDs shared by the browser, AI Service and Knowledge Service.

IDs are labels only: they never carry identity, authorization, prompts or
credentials. All accepted values must match the same allowlisted pattern as
``agent.runtime_events``.
"""
from __future__ import annotations

import re
from uuid import uuid4

REQUEST_HEADER = "X-Request-ID"
TASK_HEADER = "X-Task-ID"
RUN_HEADER = "X-Run-ID"

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z")


def valid_id(value: object) -> str | None:
    return value if isinstance(value, str) and _ID.fullmatch(value) else None


def resolve_ids(
    *,
    header_request_id: str | None = None,
    header_task_id: str | None = None,
    header_run_id: str | None = None,
    metadata: dict | None = None,
) -> tuple[str, str, str]:
    """Return ``(request_id, task_id, run_id)``.

    The browser body metadata is still authoritative for legacy callers;
    headers are the fallback and the only source for ``run_id``.
    """
    metadata = metadata or {}
    request_id = (
        valid_id(metadata.get("request_id"))
        or valid_id(header_request_id)
        or uuid4().hex
    )
    task_id = (
        valid_id(metadata.get("task_id"))
        or valid_id(header_task_id)
        or request_id
    )
    run_id = valid_id(header_run_id) or uuid4().hex
    return request_id, task_id, run_id


def correlation_headers(
    request_id: str | None = None,
    task_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, str]:
    pairs = (
        (REQUEST_HEADER, request_id),
        (TASK_HEADER, task_id),
        (RUN_HEADER, run_id),
    )
    return {name: value for name, value in pairs if valid_id(value)}

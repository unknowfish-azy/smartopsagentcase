"""SEC-01/SEC-02: verify the short-lived chat run token issued by the Java edge.

The AI service trusts only the signed payload. Client supplied ``X-Run-ID`` is
a label, never identity; when a token is required it is ignored entirely.

Format (shared with ``com.smartops.security.RunTokenService``):
``v1.<base64url(payload)>.<base64url(hmac_sha256("v1." + payload))>``.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import time

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z")
_SUBJECT = re.compile(r"[0-9]{1,19}\Z")
_HEADER = "X-Run-Token"


class RunTokenError(Exception):
    """A rejected token, carrying the HTTP status the edge must return."""

    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def verify_run_token(token: str | None, secret: str, *, now: float | None = None) -> dict:
    if not secret:
        # fail-closed: no shared secret means no verifiable caller.
        raise RunTokenError("CHAT_RUN_TOKEN_NOT_CONFIGURED", 503)
    if not token:
        raise RunTokenError("RUN_TOKEN_REQUIRED", 401)
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != "v1":
        raise RunTokenError("RUN_TOKEN_INVALID", 401)
    signing_input = f"v1.{parts[1]}".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    try:
        supplied = _decode(parts[2])
    except (binascii.Error, ValueError):
        raise RunTokenError("RUN_TOKEN_INVALID", 401) from None
    if not hmac.compare_digest(expected, supplied):
        raise RunTokenError("RUN_TOKEN_INVALID", 401)
    try:
        payload = json.loads(_decode(parts[1]))
    except (binascii.Error, ValueError, json.JSONDecodeError):
        raise RunTokenError("RUN_TOKEN_INVALID", 401) from None
    if not isinstance(payload, dict):
        raise RunTokenError("RUN_TOKEN_INVALID", 401)
    subject = payload.get("sub")
    run_id = payload.get("run")
    expires_at = payload.get("exp")
    if not isinstance(subject, str) or not _SUBJECT.match(subject):
        raise RunTokenError("RUN_TOKEN_INVALID", 401)
    if not isinstance(run_id, str) or not _ID.match(run_id):
        raise RunTokenError("RUN_TOKEN_INVALID", 401)
    if not isinstance(expires_at, int) or isinstance(expires_at, bool):
        raise RunTokenError("RUN_TOKEN_INVALID", 401)
    if expires_at <= int(time.time() if now is None else now):
        raise RunTokenError("RUN_TOKEN_EXPIRED", 401)
    return {"subject": subject, "run_id": run_id, "expires_at": expires_at}


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

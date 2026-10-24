"""Safe REAL-model health check; secrets are only read in memory."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from training.readiness.model_check import _safe_model_config, _env_key_present


def _health_url(provider: str, base_url: str) -> str:
    base = base_url.rstrip("/")
    if provider == "ollama":
        return f"{base or 'http://127.0.0.1:11434'}/api/tags"
    return f"{base}/models"


def check_real_model(timeout: float = 3.0) -> dict[str, Any]:
    cfg = _safe_model_config()
    provider = cfg["LLM_PROVIDER"].strip().lower()
    model = cfg["LLM_MODEL"].strip()
    base_url = cfg["LLM_BASE_URL"].strip()
    result: dict[str, Any] = {"provider": "PASS" if provider and provider != "mock" else "BLOCKED", "base_url": "PASS" if base_url or provider == "ollama" else "BLOCKED", "model": "PASS" if model else "BLOCKED", "connectivity": "NOT_RUN", "response": "NOT_RUN", "tool_calling": "WARN", "structured_output": "WARN"}
    if provider in {"", "mock"} or not model or (provider != "ollama" and not base_url):
        result["overall"] = "BLOCKED"
        result["reason"] = "REAL provider, base URL and model are required"
        return result
    url = _health_url(provider, base_url)
    headers = {}
    if _env_key_present("LLM_API_KEY"):
        key = os.getenv("LLM_API_KEY", "")
        if not key:
            try:
                for line in Path(".env").read_text(encoding="utf-8").splitlines():
                    if line.startswith("LLM_API_KEY="):
                        key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
            except (OSError, UnicodeError):
                key = ""
        if key:
            headers["Authorization"] = f"Bearer {key}"
    try:
        request = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result["connectivity"] = "PASS" if 200 <= response.status < 300 else "BLOCKED"
            result["response"] = "PASS" if response.read(4096) else "WARN"
    except (urllib.error.URLError, TimeoutError, OSError):
        result["connectivity"] = "BLOCKED"
        result["response"] = "NOT_RUN"
    result["overall"] = "READY" if result["connectivity"] == "PASS" and result["response"] == "PASS" else "BLOCKED"
    result["reason"] = "live provider health endpoint checked; tool calling requires a separate non-mutating probe"
    return result


if __name__ == "__main__":
    print(json.dumps(check_real_model(), ensure_ascii=False, indent=2))

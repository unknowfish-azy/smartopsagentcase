"""Model configuration checks. Secret values are never returned."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _safe_model_config() -> dict[str, str]:
    """Read only model metadata from .env; never retain secret values."""
    values = {key: os.getenv(key, "") for key in ("LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "MODEL_PATH")}
    env_file = Path(".env")
    if env_file.exists():
        try:
            for raw_line in env_file.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if key in values and not values[key]:
                    values[key] = value.strip().strip('"').strip("'")
        except (OSError, UnicodeError):
            pass
    return values


def check_model() -> dict[str, Any]:
    config = _safe_model_config()
    provider = config["LLM_PROVIDER"].strip().lower()
    model = config["LLM_MODEL"].strip()
    base_url = config["LLM_BASE_URL"].strip()
    configured = bool(provider and model)
    supported = provider in {"ollama", "openai-compatible", "openai_compatible"}
    is_mock = provider == "mock"
    model_path = config["MODEL_PATH"].strip()
    local_path_exists = bool(model_path) and Path(model_path).expanduser().exists()
    if supported and configured:
        # Configuration alone is not a real-model readiness proof. The
        # network/response probe is intentionally separate in check_model.py.
        status = "PARTIAL"
        reason = "provider and model are configured; run training.scripts.check_model for live connectivity"
    elif is_mock:
        status = "PARTIAL"
        reason = "Mock provider is configured; it is not a REAL model baseline"
    elif local_path_exists:
        status = "PARTIAL"
        reason = "local model path exists; runtime response validation is still required"
    else:
        status = "BLOCKED"
        reason = "no supported real model provider or existing local model path"
    return {
        "status": status,
        "provider": provider or None,
        "model_configured": bool(model),
        "base_url_configured": bool(base_url),
        "local_model_path_configured": bool(model_path),
        "local_model_path_exists": local_path_exists,
        "api_key_configured": bool(os.getenv("LLM_API_KEY", "").strip()) or _env_key_present("LLM_API_KEY"),
        "reason": reason,
    }


def _env_key_present(key: str) -> bool:
    """Check secret key presence without returning or logging its value."""
    if os.getenv(key, "").strip():
        return True
    env_file = Path(".env")
    if not env_file.exists():
        return False
    try:
        return any(line.strip().startswith(f"{key}=") and bool(line.split("=", 1)[1].strip()) for line in env_file.read_text(encoding="utf-8").splitlines())
    except (OSError, UnicodeError):
        return False

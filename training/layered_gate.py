"""Non-secret layered gate checks for local, mock, and real execution."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

REAL_KEYS = (
    "MYSQL_USERNAME", "MYSQL_PASSWORD", "REDIS_HOST", "REDIS_PORT", "REDIS_PASSWORD",
    "SMARTOPS_API_KEY_ENCRYPTION_KEY", "SMARTOPS_INTERNAL_TOKEN", "LLM_PROVIDER",
    "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL",
)


def _present(key: str, env_file: Path) -> bool:
    if os.getenv(key, "").strip():
        return True
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(f"{key}="):
                return bool(line.split("=", 1)[1].strip().strip('"').strip("'"))
    except (OSError, UnicodeError):
        pass
    return False


def build_layered_gate(root: str | Path = ".", *, local_tests_pass: bool = True) -> dict[str, Any]:
    env_file = Path(root) / ".env"
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if not provider:
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("LLM_PROVIDER="):
                    provider = line.split("=", 1)[1].strip().strip('"').strip("'").lower()
                    break
        except (OSError, UnicodeError):
            pass
    real = {key: "PASS" if _present(key, env_file) else "MISSING" for key in REAL_KEYS}
    real_ready = provider not in {"", "mock"} and all(value == "PASS" for value in real.values())
    return {
        "LOCAL_TEST": {"status": "PASS" if local_tests_pass else "BLOCKED", "real_experiment_allowed": False},
        "MOCK": {"status": "PASS" if provider == "mock" else "WARN", "model_status": "MOCK" if provider == "mock" else "NOT_CONFIGURED", "real_experiment_allowed": False},
        "REAL_GATE": {"status": "PASS" if real_ready else "BLOCKED", "checks": real, "real_experiment_allowed": real_ready},
    }


__all__ = ["build_layered_gate"]

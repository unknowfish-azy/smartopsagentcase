"""Immutable experiment metadata helpers for Phase 7.4 baselines."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SECRET_KEYS = {"api_key", "password", "token", "secret", "ciphertext", "aes_key"}


def _assert_no_secrets(value: Any, path: str = "root") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in SECRET_KEYS:
                raise ValueError(f"secret-like field is not permitted in artifact: {path}.{key}")
            _assert_no_secrets(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_no_secrets(item, f"{path}[{index}]")


def freeze_contract(metadata: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic, non-secret contract metadata for an experiment."""
    _assert_no_secrets(metadata)
    result = dict(metadata)
    result.setdefault("evaluator_version", "v1")
    result.setdefault("ground_truth_version", "NOT_SET")
    result.setdefault("schema_version", "1.0.0")
    result["contract_hash"] = hashlib.sha256(
        json.dumps(result, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return result


def write_artifact(root: str | Path, experiment_id: str, config: dict[str, Any]) -> Path:
    """Create an immutable config artifact; existing artifacts are never overwritten."""
    _assert_no_secrets(config)
    target = Path(root) / "experiments" / experiment_id
    target.mkdir(parents=True, exist_ok=True)
    path = target / "config.json"
    if path.exists():
        raise FileExistsError(f"experiment artifact already exists: {path}")
    path.write_text(json.dumps(freeze_contract(config), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


__all__ = ["freeze_contract", "write_artifact"]

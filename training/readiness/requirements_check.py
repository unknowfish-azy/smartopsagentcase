"""Optional training dependency availability checks."""

from __future__ import annotations

import importlib.util
from typing import Any


REQUIREMENTS = ("torch", "transformers", "datasets", "peft", "trl")


def check_requirements() -> dict[str, Any]:
    packages = {name: bool(importlib.util.find_spec(name)) for name in REQUIREMENTS}
    installed = [name for name, present in packages.items() if present]
    missing = [name for name, present in packages.items() if not present]
    return {
        "status": "READY" if not missing else "PARTIAL",
        "packages": packages,
        "installed": installed,
        "missing": missing,
        "reason": "all training packages available" if not missing else "optional training packages are missing",
    }

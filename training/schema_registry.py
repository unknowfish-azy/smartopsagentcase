"""Read-only registry for versioned SmartOps training schemas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SCHEMA_DIR = Path(__file__).with_name("schemas")
CATALOG_PATH = SCHEMA_DIR / "catalog.json"


def load_catalog() -> dict[str, Any]:
    """Load the checked-in schema catalog without resolving external resources."""
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def schema_path(name: str) -> Path:
    """Resolve a catalog schema name while preventing path traversal."""
    catalog = load_catalog()
    relative = catalog.get("schemas", {}).get(name)
    if relative is None:
        raise KeyError(f"unknown training schema: {name}")
    path = (SCHEMA_DIR / relative).resolve()
    if path.parent != SCHEMA_DIR.resolve():
        raise ValueError(f"schema path escapes registry: {relative}")
    return path


def load_schema(name: str) -> dict[str, Any]:
    """Load a schema registered by its stable logical name."""
    return json.loads(schema_path(name).read_text(encoding="utf-8"))


def schema_version() -> str:
    return str(load_catalog()["schema_version"])


__all__ = ["load_catalog", "load_schema", "schema_path", "schema_version"]

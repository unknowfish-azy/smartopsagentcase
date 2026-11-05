"""Scan competition materials for metrics that must match the defense ledger."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOTS = (REPO_ROOT / "docs" / "competition", REPO_ROOT / "README.md")
DEFAULT_OUTPUT = REPO_ROOT / "06-工程整改" / "numeric_consistency.csv"


def table_inventory(root: Path = REPO_ROOT) -> dict:
    """Count migration CREATE TABLE statements, excluding SQL comments."""
    files = sorted((root / "backend/src/main/resources/db/migration").glob("*.sql"))
    tables: dict[str, list[str]] = {}
    for path in files:
        sql = path.read_text(encoding="utf-8-sig")
        sql = re.sub(r"/\*.*?\*/|--[^\n]*", "", sql, flags=re.S)
        for name in re.findall(r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?([\w]+)`?", sql, re.I):
            tables.setdefault(name.lower(), []).append(path.name)
    return {"migration_files": len(files), "unique_create_tables": len(tables), "tables": tables}


TABLE_COUNT = str(table_inventory()["unique_create_tables"])

CANONICAL = {
    "frontend_tests": "458 collected: 456 passed, 2 failed (2026-11-03)",
    "python_total": "113 is historical; current focused regression: 55 passed",
    "python_passed": "89 is historical; current focused regression: 55 passed",
    "python_skipped": "24 is historical; do not combine with current focused regression",
    "backend_tests": "448 run: 0 failures, 0 errors, 1 skipped (2026-11-03)",
    "dataset_samples": "14",
    "dataset_files": "7",
    "table_count": f"{TABLE_COUNT} migration-defined tables; runtime DB count unverified",
    "blacklist_count": "23",
    "inspector_levels": "4",
}

PATTERNS = {
    "frontend_tests": re.compile(r"(?<!\d)458(?!\d)"),
    "python_total": re.compile(r"(?<!\d)113(?!\d)"),
    "python_passed": re.compile(r"(?<!\d)89(?!\d)"),
    "python_skipped": re.compile(r"(?<!\d)24(?!\d)"),
    "backend_tests": re.compile(r"(?<!\d)(?:428|444|448)(?!\d)"),
    "dataset_samples": re.compile(r"(?<!\d)14(?!\d)"),
    "dataset_files": re.compile(r"(?<!\d)7(?!\d)"),
    "table_count": re.compile(r"(?<!\d)(?:75|79|80|81)(?!\d)"),
    "blacklist_count": re.compile(r"(?<!\d)(?:23|25)(?!\d)"),
    "inspector_levels": re.compile(r"(?:三级|四级|3\s*级|4\s*级)"),
}

CONTEXT_HINTS = {
    "frontend_tests": ("frontend", "前端", "test", "测试"),
    "python_total": ("python", "pytest", "测试", "用例"),
    "python_passed": ("python", "pytest", "通过", "passed"),
    "python_skipped": ("python", "pytest", "跳过", "skipped"),
    "backend_tests": ("backend", "后端", "@test", "测试", "参数化"),
    "dataset_samples": ("dataset", "数据集", "样本", "jsonl", "条"),
    "dataset_files": ("dataset", "数据集", "jsonl", "文件"),
    "table_count": ("表", "table", "数据库"),
    "blacklist_count": ("黑名单", "blacklist"),
    "inspector_levels": ("纠察", "inspector"),
}


def iter_files(roots: tuple[Path, ...]):
    for root in roots:
        if root.is_file():
            yield root
            continue
        if not root.is_dir():
            continue
        yield from sorted(
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in {".md", ".txt", ".html"}
        )


def scan(roots: tuple[Path, ...]) -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    seen: set[tuple[Path, int, str]] = set()
    for path in iter_files(roots):
        try:
            lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        except OSError:
            continue
        for line_no, line in enumerate(lines, start=1):
            for metric, pattern in PATTERNS.items():
                lowered = line.lower()
                if not any(hint.lower() in lowered for hint in CONTEXT_HINTS[metric]):
                    continue
                for match in pattern.finditer(line):
                    key = (path, line_no, metric)
                    if key in seen:
                        continue
                    seen.add(key)
                    token = match.group(0)
                    expected = CANONICAL[metric]
                    status = "REVIEW" if (
                        (metric == "blacklist_count" and token != expected)
                        or (metric == "table_count" and token != TABLE_COUNT)
                        or (metric == "backend_tests" and token != "448")
                        or metric in {"python_total", "python_passed", "python_skipped"}
                        or (metric == "frontend_tests" and bool(re.search(r"全过|全通|全.{0,3}通过|all.{0,3}pass", line, re.I)))
                        or (metric == "inspector_levels" and token in {"三级", "3级"})
                    ) else "OK"
                    rows.append({
                        "file": str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path),
                        "line": line_no,
                        "metric": metric,
                        "token": token,
                        "canonical": expected,
                        "status": status,
                        "context": line.strip()[:500],
                    })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--roots", nargs="*", type=Path, default=list(DEFAULT_ROOTS))
    args = parser.parse_args()
    roots = tuple(path if path.is_absolute() else REPO_ROOT / path for path in args.roots)
    rows = scan(roots)
    output = args.output if args.output.is_absolute() else REPO_ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["file", "line", "metric", "token", "canonical", "status", "context"])
        writer.writeheader()
        writer.writerows(rows)
    review_count = sum(row["status"] == "REVIEW" for row in rows)
    print(f"CSV: {output}")
    print(f"Occurrences: {len(rows)}; review findings: {review_count}")
    output.with_name("table_inventory.json").write_text(
        json.dumps(table_inventory(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Migration inventory: {TABLE_COUNT} unique CREATE TABLE names (SQL comments excluded).")
    print("Numeric matches identify wording only; OK does not certify a test passed. Use the dated verification ledger.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

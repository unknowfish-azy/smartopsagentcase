#!/usr/bin/env python3
"""Scan competition materials for identifiers that should be anonymised.

The scanner is intentionally read-only.  It reports textual matches and image
files; the poster area is not included in the default roots.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import zipfile
from pathlib import Path
from typing import Iterable


TEXT_EXTENSIONS = {
    ".md", ".markdown", ".txt", ".html", ".htm", ".css", ".js", ".ts",
    ".json", ".yaml", ".yml", ".csv", ".xml", ".tex", ".py",
}
IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".ico",
    ".tif", ".tiff",
}
ARCHIVE_TEXT_EXTENSIONS = {".pptx", ".pptm", ".docx", ".docm", ".xlsx", ".xlsm"}

# Keep patterns broad enough to catch real school names while also catching
# explicit placeholders/labels used on title pages.
TEXT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "school_name",
        re.compile(
            r"(?:学校(?:名称|名)?|院校(?:名称|名)?|"
            r"[\u4e00-\u9fff]{2,24}(?:大学|学院|职业技术学院|职业学院|高等专科学校|专科学校))"
        ),
    ),
    (
        "adviser_keyword",
        re.compile(r"指导教师|指导老师|导师|教师指导|advisor|mentor|supervisor", re.I),
    ),
)
LOGO_NAME_PATTERN = re.compile(r"(?:校徽|校标|徽标|logo|emblem|school[_ -]?badge)", re.I)


def iter_files(roots: Iterable[Path]) -> Iterable[Path]:
    """Yield files below existing roots, skipping inaccessible entries."""
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        candidates = [root] if root.is_file() else root.rglob("*")
        for path in candidates:
            try:
                if path.is_file() and path.resolve() not in seen:
                    seen.add(path.resolve())
                    yield path
            except OSError:
                continue


def scan(roots: Iterable[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in iter_files(roots):
        suffix = path.suffix.lower()
        display = str(path)
        if suffix in IMAGE_EXTENSIONS:
            rows.append({"file": display, "line_or_type": "file", "pattern": "image_file"})
            if LOGO_NAME_PATTERN.search(path.name):
                rows.append({"file": display, "line_or_type": "file", "pattern": "logo_image"})
            continue
        if suffix not in TEXT_EXTENSIONS:
            if suffix in ARCHIVE_TEXT_EXTENSIONS:
                rows.extend(scan_archive(path))
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for label, pattern in TEXT_PATTERNS:
                if pattern.search(line):
                    rows.append({"file": display, "line_or_type": str(lineno), "pattern": label})
    return rows


def scan_archive(path: Path) -> list[dict[str, str]]:
    """Inspect XML/text members inside Office Open XML containers."""
    rows: list[dict[str, str]] = []
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile):
        return rows
    with archive:
        for member in archive.namelist():
            if Path(member).suffix.lower() not in TEXT_EXTENSIONS | {".rels"}:
                continue
            try:
                text = archive.read(member).decode("utf-8", errors="replace")
            except (OSError, KeyError):
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                for label, pattern in TEXT_PATTERNS:
                    if pattern.search(line):
                        rows.append({
                            "file": f"{path}::{member}",
                            "line_or_type": str(lineno),
                            "pattern": label,
                        })
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--roots", nargs="+", type=Path,
        help="directories/files to scan (defaults to competition, PPT and recording folders)",
    )
    parser.add_argument("--output", type=Path, default=Path("06-工程整改/anonymity_scan.csv"))
    args = parser.parse_args(argv)

    base = Path.cwd()
    roots = args.roots or [
        base / "docs" / "competition",
        Path('E:/Projects/SmartOpsAgent-Defense/02-答辩PPT'),
        Path('E:/Projects/SmartOpsAgent-Defense/04-演示与录屏'),
    ]
    roots = [p if p.is_absolute() else base / p for p in roots]
    rows = scan(roots)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["file", "line_or_type", "pattern"])
        writer.writeheader()
        writer.writerows(rows)
    writer = csv.writer(sys.stdout)
    writer.writerow(["file", "line_or_type", "pattern"])
    writer.writerows((row["file"], row["line_or_type"], row["pattern"]) for row in rows)
    print(f"scanned_roots={len(roots)} matches={len(rows)} output={args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

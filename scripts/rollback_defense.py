"""Restore only remediation files from the verified Work Buddy snapshot.

Default is a read-only preflight. --apply preserves current files in quarantine.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
import zipfile


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rollback(root: Path, bundle: Path, *, apply: bool = False) -> int:
    root = root.resolve()
    with zipfile.ZipFile(bundle) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        prepared = []
        for item in manifest["files"]:
            relative = Path(item["path"])
            target = (root / relative).resolve()
            if relative.is_absolute() or not target.is_relative_to(root):
                raise ValueError(f"Invalid rollback path: {relative}")
            if not target.is_file() or digest(target.read_bytes()) != item["after_sha256"]:
                raise ValueError(f"File changed since delivery; no files restored: {relative}")
            baseline = None
            if item["before_sha256"] is not None:
                baseline = archive.read("before/" + relative.as_posix())
                if digest(baseline) != item["before_sha256"]:
                    raise ValueError(f"Baseline hash mismatch: {relative}")
            prepared.append((relative, target, baseline))
        print(f"Preflight OK: {len(prepared)} scoped files; baseline={manifest['baseline']}")
        if not apply:
            print("Read-only check. Use --apply to restore; current files will be quarantined.")
            return 0
        quarantine = root / ".runtime" / "defense-rollback" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        for relative, target, baseline in prepared:
            saved = quarantine / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            target.replace(saved)
            if baseline is not None:
                target.write_bytes(baseline)
        print(f"Restored {len(prepared)} files. Previous contents preserved: {quarantine}")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        return rollback(args.root, args.bundle, apply=args.apply)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"Rollback stopped: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())

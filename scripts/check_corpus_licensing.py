"""Check corpus licensing: registry CSV vs on-disk reference files.

Reads P0-DATA-02-artifact_registry.csv, finds knowledge_corpus rows,
verifies on-disk paths still exist, flags mismatches.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parents[1]

def load_registry(registry_path: Path) -> list[dict]:
    with open(registry_path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def check(registry_path: Path, corpus_root: Path) -> dict:
    rows = load_registry(registry_path)
    out = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "registry_path": str(registry_path.relative_to(REPO)),
        "total_registry_rows": len(rows),
        "registry_by_category": dict(Counter(r["category"] for r in rows)),
        "issues": [],
        "summary": {},
    }
    rh = [r for r in rows if r["artifact_id"] in {"ART-001", "ART-002", "ART-003"}]

    # 1. RH dirs on disk? (should NOT exist now)
    for r in rh:
        p = Path(r["origin_url"])
        exists = p.exists()
        if r["status"] == "REJECTED" and exists:
            out["issues"].append({
                "type": "WITHDRAWN_STILL_ON_DISK",
                "artifact_id": r["artifact_id"],
                "path": str(p),
                "severity": "HIGH",
                "detail": f"Registry says REJECTED but path still exists on disk — remove now",
            })
        elif r["status"] == "REJECTED" and not exists:
            out["issues"].append({
                "type": "WITHDRAWN_AND_GONE",
                "artifact_id": r["artifact_id"],
                "path": str(p),
                "severity": "INFO",
                "detail": "Correctly withdrawn from disk",
            })

    # 2. Approved knowledge_corpus paths: must exist
    approved_corpus = [r for r in rows if r["category"] == "knowledge_corpus" and r["status"] == "APPROVED"]
    for r in approved_corpus:
        p = Path(r["origin_url"])
        if not p.exists():
            out["issues"].append({
                "type": "APPROVED_BUT_MISSING",
                "artifact_id": r["artifact_id"],
                "path": str(p),
                "severity": "MEDIUM",
                "detail": "Registry APPROVED but path not on disk",
            })

    # 3. PENDING knowledge_corpus paths: must exist
    pending_corpus = [r for r in rows if r["category"] == "knowledge_corpus" and r["status"] == "PENDING"]
    for r in pending_corpus:
        p = Path(r["origin_url"])
        if not p.exists():
            out["issues"].append({
                "type": "PENDING_AND_MISSING",
                "artifact_id": r["artifact_id"],
                "path": str(p),
                "severity": "LOW",
                "detail": "Registry PENDING and path not on disk (may be planned)",
            })

    # 4. Scan knowledge/reference for any Red Hat/IBM copyright watermark on disk
    #    (heuristic: check README files for "Red Hat" / "Internal use only" patterns)
    on_disk_docs = list(corpus_root.rglob("*.md"))
    rejected_watermarks = []
    watermark_patterns = ["internal use only", "not for sale", "red hat", "no part may be stored"]
    for md in on_disk_docs:
        try:
            text = md.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        matches = [w for w in watermark_patterns if w in text]
        if matches:
            rel = str(md.relative_to(REPO))
            rejected_watermarks.append({"path": rel, "matches": matches})
    if rejected_watermarks:
        out["issues"].append({
            "type": "ON_DISK_COPYRIGHT_WATERMARK",
            "severity": "HIGH" if any("internal use" in (m if isinstance(m, str) else "").lower() for item in rejected_watermarks for m in item["matches"]) else "MEDIUM",
            "detail": f"{len(rejected_watermarks)} doc files on disk contain rejected-corpus watermark patterns",
            "examples": rejected_watermarks[:5],
        })

    # 5. Summary
    issue_types = Counter(i["type"] for i in out["issues"])
    issue_severity = Counter(i.get("severity", "LOW") for i in out["issues"])
    out["summary"] = {
        "issue_count": len(out["issues"]),
        "by_type": dict(issue_types),
        "by_severity": dict(issue_severity),
        "approved_corpus_on_disk": len([i for i in out["issues"] if i.get("type") == "WITHDRAWN_AND_GONE"]),
    }
    return out

def main():
    import argparse, json
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path,
                        default=REPO / "docs" / "development" / "P0-DATA-02-artifact_registry.csv")
    parser.add_argument("--corpus-root", type=Path,
                        default=REPO / "knowledge" / "reference")
    parser.add_argument("--filter", default=None, help="Optional category filter")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    result = check(args.registry, args.corpus_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nWrote {args.output}")

    # Exit non-zero if HIGH severity issues exist (for CI gate)
    any_high = any(i.get("severity") == "HIGH" for i in result["issues"])
    if any_high:
        print("\n⚠️  HIGH severity issues found — review immediately")
        return 1
    print("\n✅ No HIGH severity issues")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

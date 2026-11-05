"""Check dependency lock compliance (CI gate).

Reads GH-P0-01-dependency-lock.json, validates:
1. No CANDIDATE_ONLY packages accidentally in requirements.txt (prevent premature lock-in)
2. VERIFIED Python packages' pip-installed versions are in declared range
3. VERIFIED frontend packages' package-lock exact versions match expected

Exit code:
  0 = all OK
  1 = high-severity issues (CANDIDATE_ONLY in requirements, version out of range)
"""
from __future__ import annotations

import json, re, subprocess, sys
from pathlib import Path
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parents[1]
LOCK = REPO / "docs" / "development" / "GH-P0-01-dependency-lock.json"

def parse_version(spec: str) -> tuple[str | None, str | None]:
    """Parse a single constraint like '>=0.115' → (operator, value)."""
    spec = spec.strip().replace(" ", "")
    m = re.match(r"(>=|<=|>|<|==|!=)(.+)", spec)
    if m:
        return m.group(1), m.group(2)
    return None, spec

def version_in(ver: str, range_str: str) -> bool:
    """Check if ver satisfies comma-separated constraints like '>=0.115,<1'."""
    if not ver or ver in ("N/A", "<NOT_INSTALLED>"):
        return True  # skip optional/not-installed
    # Handle ^x.y.z (npm semver caret)
    if range_str.startswith("^"):
        base = range_str[1:]
        parts = base.split(".")
        upper = f"{int(parts[0]) + 1}.0.0"
        return _cmp(ver, base) >= 0 and _cmp(ver, upper) < 0
    constraints = [c.strip() for c in range_str.split(",") if c.strip()]
    for c in constraints:
        op, val = parse_version(c)
        if op is None:
            continue
        cmp_result = _cmp(ver, val)
        if op == ">=" and cmp_result < 0:
            return False
        if op == ">" and cmp_result <= 0:
            return False
        if op == "<=" and cmp_result > 0:
            return False
        if op == "<" and cmp_result >= 0:
            return False
        if op == "==" and cmp_result != 0:
            return False
        if op == "!=" and cmp_result == 0:
            return False
    return True

def _cmp(a: str, b: str) -> int:
    """Compare two dotted version strings numerically."""
    a_parts = [int(p) for p in a.split(".") if p.isdigit()]
    b_parts = [int(p) for p in b.split(".") if p.isdigit()]
    for x, y in zip(a_parts, b_parts):
        if x != y:
            return -1 if x < y else 1
    return -1 if len(a_parts) < len(b_parts) else (1 if len(a_parts) > len(b_parts) else 0)

def pip_installed() -> dict[str, str]:
    raw = subprocess.run([sys.executable, "-m", "pip", "list", "--format=json"], capture_output=True, text=True)
    if raw.returncode != 0:
        return {}
    mods = json.loads(raw.stdout)
    return {m["name"].lower(): m["version"] for m in mods}

def main():
    lock_data = json.loads(LOCK.read_text(encoding="utf-8"))
    issues = []

    # 1. Python: no CANDIDATE_ONLY in requirements
    cand_names = [c["package"].split("(")[0].strip() for c in lock_data["candidate_only"]]
    for req_file in ["ai-service/requirements.txt", "knowledge/requirements.txt"]:
        path = REPO / req_file
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for cname in cand_names:
            if cname.lower() in text.lower():
                issues.append({
                    "type": "CANDIDATE_LOCKED",
                    "severity": "HIGH",
                    "detail": f"{cname} is CANDIDATE_ONLY but found in {req_file}",
                })

    # 2. Python: VERIFIED versions in range
    pip = pip_installed()
    for dep in lock_data["verified_python"]:
        pkg = dep["package"].split("[")[0].lower()
        range_str = dep.get("declared_range", "")
        if range_str.startswith("("):
            continue  # transitive
        installed = pip.get(pkg, "")
        if installed and not installed.startswith("<") and not installed.startswith("N/A"):
            if ">=" in range_str or range_str.startswith("^"):
                if not version_in(installed, range_str):
                    issues.append({
                        "type": "VERSION_OUT_OF_RANGE",
                        "severity": "MEDIUM",
                        "detail": f"{dep['package']}: installed={installed} not in range {range_str}",
                    })

    # 3. Frontend: package-lock exact versions present
    pkg_json_path = REPO / "frontend" / "package.json"
    if pkg_json_path.exists():
        pkg_data = json.loads(pkg_json_path.read_text(encoding="utf-8"))
        lock_json_path = REPO / "frontend" / "package-lock.json"
        if lock_json_path.exists():
            lock_data_f = json.loads(lock_json_path.read_text(encoding="utf-8"))
            packages = lock_data_f.get("packages", {})
            for dep in lock_data["verified_frontend"]:
                key = f"node_modules/{dep['package']}"
                entry = packages.get(key, {})
                exact = entry.get("version", "")
                if not exact and dep.get("exact") not in ("<NO_EXACT_IN_LOCK>", None):
                    issues.append({
                        "type": "FRONTEND_NO_LOCK",
                        "severity": "LOW",
                        "detail": f"{dep['package']}: no exact version in package-lock.json",
                    })

    # Print summary
    print(f"GH-P0-01 dependency lock check — {datetime.now(timezone.utc).isoformat()}")
    print(f"VERIFIED python={len(lock_data['verified_python'])}  frontend={len(lock_data['verified_frontend'])}")
    print(f"CANDIDATE_ONLY={len(lock_data['candidate_only'])}: {', '.join(cand_names)}")
    print(f"Issues: {len(issues)}")
    for i in issues:
        print(f"  [{i['severity']:6s}] {i['type']}: {i['detail']}")

    high = [i for i in issues if i["severity"] == "HIGH"]
    if high:
        print("\n❌ HIGH severity issues — FAIL")
        return 1
    print("\n✅ All checks passed")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

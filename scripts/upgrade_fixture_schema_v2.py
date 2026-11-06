"""一次性升级 fixture schema 1→2。保留原 label/probes 完全不变；只加治理元数据。

用法：python scripts/upgrade_fixture_schema_v2.py
"""
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# 当前两份 fixture 全部标记为 synthetic_dev / unreviewed。
# 任务书明确："受控原型不等人工 Golden 完备；正式效果结论须有独立人工审核"，
# 所以本轮不虚构人工审核状态，也不接真实观测。
PER_CASE_DEFAULTS = {
    "label_source": "synthetic_dev",
    "license": "MIT-synthetic",
    "pii": False,
    "review_status": "unreviewed",
    "evidence_hash": None,
    "duplicate_of": None,
}

TOPLEVEL_PROVENANCE = {
    "source_type": "synthetic_dev",
    "source_id": "eval_false_success_synthetic_v2",
    "license": "MIT-synthetic",
    "pii_contained": False,
    "created_at": "2026-11-06",
    "created_by": "DATA-P0-01 fixture governance (not human-reviewed)",
    "curation_hash": None,  # 升级完后回填
    "notes": (
        "Developed synthetically for SCORE-P0-01 false-success fixture suite. "
        "No human Golden, no live observation, no PII. Labels are unit-testable "
        "assertions against probes; do not claim real-world distribution fit."
    ),
}


def upgrade_case(case: dict) -> dict:
    """保留 v1 全部字段；新增 v2 治理字段；不修改 label/probes。"""
    new = dict(case)
    for k, v in PER_CASE_DEFAULTS.items():
        new.setdefault(k, v)
    return new


def upgrade_fixture(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    old_prov = raw.get("provenance")
    cases = raw["cases"]

    new_prov = dict(TOPLEVEL_PROVENANCE)
    new_prov["legacy_provenance_text"] = old_prov if isinstance(old_prov, str) else None

    # 先升级 case，用升级后的 case 计算 curation_hash
    upgraded_cases = [upgrade_case(c) for c in cases]
    sorted_for_hash = sorted(
        json.dumps(c, ensure_ascii=False, sort_keys=True) for c in upgraded_cases
    )
    new_prov["curation_hash"] = hashlib.sha256(
        ("\n".join(sorted_for_hash)).encode("utf-8")
    ).hexdigest()

    out = {
        "schema_version": 2,
        "provenance": new_prov,
        "limitations": raw.get("limitations", ""),
        "cases": upgraded_cases,
    }
    # 保留顶层 note（holdout fixture 有，main 没有）
    if "note" in raw:
        out["note"] = raw["note"]
    return out


def main():
    targets = [
        REPO / "tests/fixtures/defense/false_success.json",
        REPO / "tests/fixtures/defense/false_success_holdout.json",
    ]
    for path in targets:
        if not path.exists():
            print(f"SKIP {path} not found", file=sys.stderr)
            continue
        new = upgrade_fixture(path)
        path.write_text(
            json.dumps(new, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            f"UPGRADED {path} → schema v2, "
            f"cases={len(new['cases'])}, "
            f"curation_hash={new['provenance']['curation_hash'][:16]}…"
        )


if __name__ == "__main__":
    main()

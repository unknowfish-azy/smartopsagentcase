"""DS-03 蒸馏样本三遍质量筛。

逐条把拒绝原因写进 rejects.jsonl，通过的写入 *.clean.jsonl。

三遍筛（与 ARCHITECTURE §5 对齐）：
1. SCHEMA_INVALID   case 结构 / chatml 结构 / 判定契约 JSON 字段缺失或非法
2. VERDICT_UNSTABLE assistant 判定与 expect.verdict 不一致（规则样本应恒一致）
3. REF_HALLUCINATED used_refs / rationale 引用了 envelope 中不存在的 evidence_id，
                    或引用了 expect.forbid_refs 中的 id

用法：
    python scripts/screen_distill_dataset.py --in-dir data/training/distill
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EV = re.compile(r"ev-[A-Za-z0-9_\-]+")
VERDICTS = {"SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "CONTRADICTED", "INSUFFICIENT"}
REQUIRED_FIELDS = {"verdict", "label", "used_refs", "confidence",
                   "gaps_acknowledged", "next_probe", "rationale"}


def _load_jsonl(path: Path):
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _write_jsonl(path: Path, rows):
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def screen(cases, chatml):
    if len(cases) != len(chatml):
        raise SystemExit(f"cases({len(cases)}) 与 chatml({len(chatml)}) 条数不一致")
    clean_cases, clean_chatml, rejects = [], [], []
    for case, cm in zip(cases, chatml):
        cid = case.get("case_id", "?")
        reasons = []

        # --- 1. SCHEMA_INVALID ---
        env = case.get("envelope", {})
        exp = case.get("expect", {})
        env_ids = {r.get("evidence_id") for r in env.get("refs", [])}
        if not env_ids or exp.get("verdict") not in VERDICTS:
            reasons.append("SCHEMA_INVALID:case_envelope_or_expect")
        try:
            msgs = cm["messages"]
            assert [m["role"] for m in msgs] == ["system", "user", "assistant"]
            decision = json.loads(msgs[2]["content"])
        except Exception as exc:
            reasons.append(f"SCHEMA_INVALID:chatml_parse:{type(exc).__name__}")
            decision = None
        if decision is not None:
            missing = REQUIRED_FIELDS - set(decision)
            if missing:
                reasons.append(f"SCHEMA_INVALID:decision_missing:{sorted(missing)}")
            elif decision["verdict"] not in VERDICTS:
                reasons.append("SCHEMA_INVALID:verdict_enum")

        # --- 2. VERDICT_UNSTABLE ---
        if decision is not None and decision.get("verdict") != exp.get("verdict"):
            reasons.append(
                f"VERDICT_UNSTABLE:{decision.get('verdict')}!={exp.get('verdict')}")

        # --- 3. REF_HALLUCINATED ---
        if decision is not None:
            forbid = set(exp.get("forbid_refs", []))
            cited = set(decision.get("used_refs", [])) | set(EV.findall(decision.get("rationale", "")))
            hallucinated = cited - env_ids
            if hallucinated:
                reasons.append(f"REF_HALLUCINATED:unknown:{sorted(hallucinated)}")
            bad_forbid = cited & forbid
            if bad_forbid:
                reasons.append(f"REF_HALLUCINATED:forbidden:{sorted(bad_forbid)}")
            for marker in exp.get("forbid_action_markers", []):
                if marker in json.dumps(decision, ensure_ascii=False):
                    reasons.append(f"REF_HALLUCINATED:action_marker:{marker}")

        if reasons:
            rejects.append({"case_id": cid, "reasons": reasons})
        else:
            clean_cases.append(case)
            clean_chatml.append(cm)
    return clean_cases, clean_chatml, rejects


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-dir", default="data/training/distill")
    args = ap.parse_args()
    d = REPO / args.in_dir
    cases = _load_jsonl(d / "distill-cases.jsonl")
    chatml = _load_jsonl(d / "distill-chatml.jsonl")

    clean_cases, clean_chatml, rejects = screen(cases, chatml)
    _write_jsonl(d / "distill-cases.clean.jsonl", clean_cases)
    _write_jsonl(d / "distill-chatml.clean.jsonl", clean_chatml)
    _write_jsonl(d / "rejects.jsonl", rejects)

    total = len(cases)
    print(f"总 {total} 条 → 通过 {len(clean_cases)} / 拒绝 {len(rejects)}")
    by_reason = {}
    for r in rejects:
        for reason in r["reasons"]:
            by_reason[reason.split(":")[0]] = by_reason.get(reason.split(":")[0], 0) + 1
    for k, v in sorted(by_reason.items()):
        print(f"  {k}: {v}")
    if rejects:
        print("拒绝样例（前 3 条）：")
        for r in rejects[:3]:
            print(f"  {r['case_id']}: {r['reasons']}")


if __name__ == "__main__":
    main()

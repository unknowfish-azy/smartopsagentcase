"""结果注册表：把所有实验产物登记成一份可机器核对的清单。

条目字段
--------
``key``        实验/产物标识
``path``       仓库相对路径
``kind``       ``dataset`` / ``split`` / ``experiment`` / ``diagnostic``
``required``   False 时缺失只警告、不判失败
``status``     从产物 JSON 里读出的状态（读不到为 null）
``n``          样本量（读不到为 null）
``seed``       种子（读不到为 null）
``sha256``     产物内容哈希（前 16 位）
``size_bytes`` 文件字节数

用法：``python repro/registry.py`` 打印 JSON，或 ``build_registry()`` 供 reproduce 调用。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "repro" / "registry.json"

DATASET_DIR = REPO / "SmartOps-Dataset" / "Controlled" / "v1"
REPORTS = REPO / "reports"

# 产物清单：key -> (相对路径, kind, required)
ARTIFACTS: list[dict[str, Any]] = [
    {"key": "dataset_samples", "path": "SmartOps-Dataset/Controlled/v1/samples.jsonl",
     "kind": "dataset", "required": True},
    {"key": "dataset_card", "path": "SmartOps-Dataset/Controlled/v1/DATA-CARD.md",
     "kind": "dataset", "required": True},
    {"key": "split_train", "path": "SmartOps-Dataset/Controlled/v1/splits/train.jsonl",
     "kind": "split", "required": True},
    {"key": "split_validation", "path": "SmartOps-Dataset/Controlled/v1/splits/validation.jsonl",
     "kind": "split", "required": True},
    {"key": "split_test", "path": "SmartOps-Dataset/Controlled/v1/splits/test.jsonl",
     "kind": "split", "required": True},
    {"key": "leakage_grouped", "path": "reports/leakage-grouped.json",
     "kind": "diagnostic", "required": True},
    {"key": "leakage_negative_control", "path": "reports/leakage-random-negative-control.json",
     "kind": "diagnostic", "required": True},
    {"key": "baseline_controlled", "path": "reports/baseline-controlled-v1.json",
     "kind": "experiment", "required": True},
    {"key": "ablation_inspector", "path": "reports/ablation-inspector-controlled.json",
     "kind": "experiment", "required": True},
    {"key": "ablation_rootcause_summary", "path": "reports/ablation_rootcause_summary.json",
     "kind": "experiment", "required": False},
    {"key": "ablation_rootcause_stats", "path": "reports/ablation-rootcause-stats.json",
     "kind": "experiment", "required": False},
    {"key": "icc_design_effect", "path": "reports/icc-design-effect.json",
     "kind": "experiment", "required": False},
    {"key": "power_dataset_sizing", "path": "reports/power-dataset-sizing.json",
     "kind": "experiment", "required": False},
    {"key": "wording_audit", "path": "reports/wording-holdout.json",
     "kind": "diagnostic", "required": False},
    # 效度审计：循环成立时脚本返回非零。登记为 diagnostic 便于注册表核对存在性，
    # 但**不**因此把既有基线指标判为无效——是否降级由报告与 fact-sheet 口径决定。
    {"key": "label_probe_circularity", "path": "reports/label-probe-circularity.json",
     "kind": "diagnostic", "required": False},
]

# 各实验产物里「状态 / 样本量 / 种子」的 JSON 路径（点号分隔）
_STATUS_KEY = {
    "baseline_controlled": "status",
    "ablation_inspector": "status",
    "ablation_rootcause_summary": None,
    "ablation_rootcause_stats": "status",
    "icc_design_effect": "status",
    "power_dataset_sizing": None,
    "wording_audit": None,
    "label_probe_circularity": None,
}
_N_KEY = {
    "baseline_controlled": "n_controlled",
    "ablation_inspector": "n_samples",
    "ablation_rootcause_summary": None,
    "ablation_rootcause_stats": "n_runs",
    "icc_design_effect": "n_configs",
    "power_dataset_sizing": None,
    "wording_audit": None,
    # 取「主指标二分类子集上被平凡规则复现的条数」，便于一眼看出循环强度
    "label_probe_circularity": "full.binary_trivial_correct",
}
_SEED_KEY = {
    "baseline_controlled": "stats.seed",
    "ablation_inspector": "stats.seed",
    "ablation_rootcause_summary": None,
    "ablation_rootcause_stats": "seed",
    "icc_design_effect": None,
    "power_dataset_sizing": None,
}


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dig(payload: Any, dotted: str | None) -> Any:
    if not dotted:
        return None
    cur = payload
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _count_jsonl(path: Path) -> int | None:
    try:
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    except OSError:
        return None


def build_registry() -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    missing: list[str] = []
    for spec in ARTIFACTS:
        path = REPO / spec["path"]
        entry: dict[str, Any] = {**spec, "exists": path.exists()}
        if not path.exists():
            if spec["required"]:
                missing.append(spec["key"])
            entries.append(entry)
            continue

        payload: Any = None
        if path.suffix == ".json":
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = None
        elif path.suffix == ".jsonl":
            entry["n"] = _count_jsonl(path)

        entry["size_bytes"] = path.stat().st_size
        entry["sha256_16"] = sha256_of(path)[:16]
        entry["status"] = _dig(payload, _STATUS_KEY.get(spec["key"]))
        entry["n"] = entry.get("n") if entry.get("n") is not None else _dig(
            payload, _N_KEY.get(spec["key"]))
        entry["seed"] = _dig(payload, _SEED_KEY.get(spec["key"]))
        entries.append(entry)

    required = [e["key"] for e in entries if e["required"]]
    present = [e["key"] for e in entries if e["exists"]]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo": REPO.name,
        "n_artifacts": len(entries),
        "n_required": len(required),
        "n_present_required": len([k for k in present if k in required]),
        "complete": not missing,
        "missing_required": missing,
        "experiments": entries,
    }


def write_registry(path: Path = DEFAULT_OUT) -> dict[str, Any]:
    payload = build_registry()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    result = write_registry()
    print(json.dumps({k: v for k, v in result.items() if k != "experiments"},
                     ensure_ascii=False, indent=2))
    for entry in result["experiments"]:
        flag = "OK " if entry["exists"] else ("MISS" if entry["required"] else "skip")
        print(f"  [{flag}] {entry['key']:<28} {str(entry.get('status')):<32} "
              f"n={entry.get('n')} sha={entry.get('sha256_16')}")

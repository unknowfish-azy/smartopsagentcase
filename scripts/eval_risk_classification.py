"""M04 口径 A：工具级风险声明一致性评测（非指令级 AI 风险识别）。

对比两个真实存在的风险来源：
  1) 声明值：核心工具类的 `risk_level` 类属性、插件 manifest.yaml 的 `risk.operations`；
  2) 分类器：`agent/policies/risk.py` 的 `RiskClassifier.classify(tool_name)`。

输出：逐操作明细 CSV + 汇总 JSON（准确率、混淆矩阵、审批高危漏放数）。

诚实边界：策略执行实际读取的是工具/manifest 声明（agent/policies/policy_engine.py:23），
本评测揭示的是"双轨不一致"这一潜在风险，不等于已发生越权执行。
"""
from __future__ import annotations

import argparse
import csv
import importlib
import inspect
import json
import sys
from collections import Counter
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.policies.risk import RiskClassifier
CORE_MODULES = ("agent.tools.knowledge", "agent.tools.server", "agent.tools.shell")
PLUGIN_DIR = REPO_ROOT / "agent" / "plugins" / "installed"
LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


def core_declarations() -> list[dict]:
    """从核心工具类读取 name + risk_level（反射，不解析源码文本）。"""
    rows = []
    for module_name in CORE_MODULES:
        module = importlib.import_module(module_name)
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            tool = getattr(obj, "name", None)
            risk = getattr(obj, "risk_level", None)
            if isinstance(tool, str) and tool and isinstance(risk, str):
                rows.append({"operation": tool, "declared": risk, "declared_source": module_name,
                             "approval_required": None})
    return rows


def plugin_declarations() -> list[dict]:
    """读取每个已安装插件 manifest 的 risk.operations；未列出的 tools 用 risk.default。"""
    rows = []
    for manifest_path in sorted(PLUGIN_DIR.glob("*/manifest.yaml")):
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        plugin = manifest_path.parent.name
        risk_block = manifest.get("risk") or {}
        default = risk_block.get("default", "MEDIUM")
        operations = {item["operation"]: item for item in risk_block.get("operations") or []}
        for operation in manifest.get("tools") or []:
            item = operations.get(operation)
            rows.append({
                "operation": operation,
                "declared": item["risk"] if item else default,
                "declared_source": f"plugin:{plugin}" + ("" if item else "(default)"),
                "approval_required": bool(item.get("approval_required")) if item else None,
            })
    return rows


def evaluate(rows: list[dict]) -> tuple[list[dict], dict]:
    classifier = RiskClassifier()
    detail = []
    confusion = Counter()
    for row in rows:
        predicted = classifier.classify(row["operation"]).value
        declared = row["declared"]
        # 审批要求为真、但分类器只给 LOW/MEDIUM：若单独依赖分类器做闸门会被漏放
        missed = bool(row["approval_required"]) and predicted in ("LOW", "MEDIUM")
        confusion[(declared, predicted)] += 1
        detail.append({**row, "classifier": predicted,
                       "match": declared == predicted, "approval_missed_by_classifier": missed})
    n = len(detail)
    matched = sum(1 for d in detail if d["match"])
    metrics = {
        "n": n,
        "coverage_note": "已安装插件与核心工具的全量枚举，非抽样",
        "accuracy": {"num": matched, "den": n, "value": round(matched / n, 4) if n else None},
        "declared_distribution": dict(Counter(d["declared"] for d in detail)),
        "classifier_distribution": dict(Counter(d["classifier"] for d in detail)),
        "confusion_matrix": {f"{d}->{p}": c for (d, p), c in sorted(confusion.items())},
        "approval_missed_by_classifier_n": sum(1 for d in detail if d["approval_missed_by_classifier"]),
        "approval_required_n": sum(1 for d in detail if d["approval_required"]),
        "mismatches": [{"operation": d["operation"], "declared": d["declared"], "classifier": d["classifier"]}
                       for d in detail if not d["match"]],
        "levels": list(LEVELS),
        "caveat": "策略执行读取工具/manifest 声明（policy_engine.py:23）；不一致=双轨风险，不等于已发生越权",
    }
    return detail, metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--metrics-json", type=Path, required=True)
    args = parser.parse_args()

    rows = core_declarations() + plugin_declarations()
    detail, metrics = evaluate(rows)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(detail[0].keys()))
        writer.writeheader()
        writer.writerows(detail)
    args.metrics_json.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"n={metrics['n']} accuracy={metrics['accuracy']['value']} "
          f"({metrics['accuracy']['num']}/{metrics['accuracy']['den']})")
    print(f"declared={metrics['declared_distribution']}")
    print(f"classifier={metrics['classifier_distribution']}")
    print(f"approval_required={metrics['approval_required_n']} "
          f"approval_missed_by_classifier={metrics['approval_missed_by_classifier_n']}")
    print(f"CSV: {args.output}\nmetrics_json: {args.metrics_json}")


if __name__ == "__main__":
    main()

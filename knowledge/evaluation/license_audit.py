"""黄金集许可证批量审核工具（P0-5 修复）。

解决 golden_set_v2.json 中 415 条 case 仅 12 条 approved、其余 pending 的问题。

用法：
    # 查看当前 license 分布
    python -m knowledge.evaluation.license_audit --dataset golden_set_v2.json --status

    # 按 corpus_dir 批量标记为 approved
    python -m knowledge.evaluation.license_audit --dataset golden_set_v2.json \\
        --approve-dir "SmartOpsAgent-项目知识"

    # 按 corpus_dir 标记为特定 license 状态
    python -m knowledge.evaluation.license_audit --dataset golden_set_v2.json \\
        --set-dir "AI-Infra" --license "pending: ART-021"

    # 只查看 approved 子集大小（用于确认对外答辩可用数据量）
    python -m knowledge.evaluation.license_audit --dataset golden_set_v2.json --approved-count
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def load_cases(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_cases(path: Path, cases: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(cases, f, ensure_ascii=False, indent=2)
        f.write("\n")


def show_status(cases: list[dict]) -> None:
    print(f"总 case 数: {len(cases)}")
    print()
    print("license_status 分布:")
    for lic, count in Counter(c.get("license_status", "MISSING") for c in cases).most_common():
        print(f"  {lic:<40} {count:>4}")
    print()
    print("corpus_dir 分布:")
    for cd, count in Counter(c.get("corpus_dir", "MISSING") for c in cases).most_common():
        print(f"  {cd:<40} {count:>4}")


def approve_by_dir(cases: list[dict], corpus_dir: str) -> int:
    updated = 0
    for case in cases:
        if case.get("corpus_dir") == corpus_dir:
            case["license_status"] = "approved"
            updated += 1
    return updated


def set_license_by_dir(cases: list[dict], corpus_dir: str, license_status: str) -> int:
    updated = 0
    for case in cases:
        if case.get("corpus_dir") == corpus_dir:
            case["license_status"] = license_status
            updated += 1
    return updated


def approved_count(cases: list[dict]) -> int:
    return sum(1 for c in cases if c.get("license_status") == "approved")


def main() -> int:
    parser = argparse.ArgumentParser(description="黄金集许可证批量审核")
    parser.add_argument("--dataset", required=True, help="黄金集 JSON 路径")
    parser.add_argument("--status", action="store_true", help="查看当前 license 分布")
    parser.add_argument("--approve-dir", default="", help="把指定 corpus_dir 的 case 标记为 approved")
    parser.add_argument("--set-dir", default="", help="把指定 corpus_dir 的 case 标记为 --license 指定的状态")
    parser.add_argument("--license", default="", help="配合 --set-dir 使用的 license 状态")
    parser.add_argument("--approved-count", action="store_true", help="只输出 approved case 数量")
    args = parser.parse_args()

    path = Path(args.dataset)
    if not path.exists():
        print(f"文件不存在: {path}", file=sys.stderr)
        return 1

    cases = load_cases(path)

    if args.approved_count:
        print(approved_count(cases))
        return 0

    if args.status:
        show_status(cases)
        return 0

    modified = False
    if args.approve_dir:
        n = approve_by_dir(cases, args.approve_dir)
        print(f"已将 corpus_dir='{args.approve_dir}' 的 {n} 条 case 标记为 approved")
        modified = True

    if args.set_dir and args.license:
        n = set_license_by_dir(cases, args.set_dir, args.license)
        print(f"已将 corpus_dir='{args.set_dir}' 的 {n} 条 case 标记为 '{args.license}'")
        modified = True

    if modified:
        save_cases(path, cases)
        print(f"已保存到 {path}")
        print(f"当前 approved 数量: {approved_count(cases)}")

    if not args.status and not args.approve_dir and not args.set_dir and not args.approved_count:
        show_status(cases)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

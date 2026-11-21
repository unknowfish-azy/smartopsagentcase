"""一键复现：从数据集指纹到全部评测产物与结果注册表。

用法
----
    python repro/reproduce.py                      # 标准复现（不含模型训练）
    python repro/reproduce.py --with-tests         # 额外跑统计/评测单测
    python repro/reproduce.py --with-rootcause     # 额外跑根因模型消融（慢，需 torch）
    python repro/reproduce.py --only-registry      # 只重建注册表（不重跑评测）

设计
----
- 每一步都用 ``sys.executable`` 调子进程，记录返回码/耗时/输出尾部。
- 任意必需步骤失败即停止，并给出**已完成步骤**与**失败步骤**的清晰分界。
- 最终产出 ``repro/environment.json`` 与 ``repro/registry.json``；
  环境 dirty（有未提交改动）时输出显式警告。
- 本脚本**不修改** ``agent/`` 下的评测语义，只按既有 CLI 调用。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
REPRO_DIR = REPO / "repro"
sys.path.insert(0, str(REPRO_DIR))

import environment  # noqa: E402
import registry  # noqa: E402

STEPS: list[dict[str, Any]] = [
    {"key": "dataset_fingerprint", "required": True,
     "cmd": ["scripts/build_controlled_dataset.py", "--check"],
     "desc": "校验受控集冻结指纹（可复现构建）"},
    {"key": "split", "required": True,
     "cmd": ["scripts/split_controlled.py"],
     "desc": "分组切分（族×标签分层，固定种子）"},
    {"key": "leakage_check", "required": True,
     "cmd": ["scripts/run_leakage_check.py"],
     "desc": "泄漏检查 + 随机负对照"},
    {"key": "baseline", "required": True,
     "cmd": ["scripts/eval_controlled_baseline.py"],
     "desc": "EXP-BASELINE-001 受控集基线（含区间/检验）"},
    {"key": "ablation_inspector", "required": True,
     "cmd": ["scripts/eval_inspector_ablation_controlled.py"],
     "desc": "EXP-ABLATION-INSPECTOR-001 层级消融"},
]

OPTIONAL_STEPS: list[dict[str, Any]] = [
    {"key": "ablation_rootcause", "required": False,
     "cmd": ["ai-service/scripts/ablation_rootcause.py"],
     "desc": "M2-3 根因模型消融（需 torch，耗时较长；产出逐事件结果）"},
    {"key": "ablation_rootcause_stats", "required": False,
     "cmd": ["scripts/ablation_rootcause_stats.py"],
     "desc": "EXP-ABLATION-ROOTCAUSE-STATS-001 统计推断（区间/配对检验/Holm）"},
    {"key": "icc_design_effect", "required": False,
     "cmd": ["scripts/icc_design_effect.py"],
     "desc": "EXP-ICC-001 分组相关 ICC / 设计效应 / 有效样本量"},
    # 效度审计：**返回非零是预期结果**（发现标签—探针循环），因此不作为必需步骤，
    # 只在 --all 时运行；这里用 --no-fail-on-audit 语义由 reproduce 特殊处理。
    {"key": "validity_audits", "required": False, "expect_nonzero": True,
     "cmd": ["scripts/build_wording_holdout.py", "--write"],
     "desc": "EXP-WORDING-001 措辞独立性审计（只落盘报告）"},
]

TEST_CMD = ["-m", "pytest", "tests/scripts/test_stats_inference.py",
            "tests/scripts/test_eval_controlled_baseline_stats.py",
            "tests/scripts/test_eval_inspector_ablation_controlled.py",
            "tests/scripts/test_ablation_rootcause_stats.py",
            "tests/scripts/test_icc_design_effect.py",
            "tests/scripts/test_validity_audits.py", "-q"]


def _run(cmd: list[str], cwd: Path = REPO) -> dict[str, Any]:
    """跑一个子进程，返回结构化结果（不抛异常）。"""
    started = time.perf_counter()
    proc = subprocess.run([sys.executable, *cmd], cwd=str(cwd), capture_output=True,
                          text=True, encoding="utf-8", errors="replace", check=False)
    elapsed = round(time.perf_counter() - started, 2)
    tail = "\n".join((proc.stdout or "").splitlines()[-6:])
    err_tail = "\n".join((proc.stderr or "").splitlines()[-6:])
    return {"cmd": cmd, "returncode": proc.returncode, "elapsed_sec": elapsed,
            "stdout_tail": tail, "stderr_tail": err_tail}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SmartOps 评测链一键复现")
    parser.add_argument("--with-tests", action="store_true", help="额外跑统计/评测单测")
    parser.add_argument("--with-rootcause", action="store_true", help="额外跑根因模型消融")
    parser.add_argument("--only-registry", action="store_true", help="只重建注册表")
    parser.add_argument("--out-dir", default=str(REPRO_DIR))
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log: list[dict[str, Any]] = []

    # 1. 环境指纹
    env = environment.collect_environment()
    (out_dir / "environment.json").write_text(
        json.dumps(env, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[env] python={env['python']['version']} "
          f"platform={env['platform']['system']}/{env['platform']['machine']} "
          f"cpus={env['platform']['cpu_count']} "
          f"mem={env['platform']['total_memory_gb']}GB")
    print(f"[env] git={env['git']['commit'][:12] if env['git']['commit'] else 'null'} "
          f"dirty={env['git']['dirty']}（{env['git']['dirty_file_count']} 个未提交文件）")
    if env["git"]["dirty"]:
        print("[env] ⚠️ 工作区有未提交改动：本结果**不是**已归档的复现状态。")

    if args.only_registry:
        result = registry.write_registry(out_dir / "registry.json")
        print(f"[registry] complete={result['complete']} "
              f"({result['n_present_required']}/{result['n_required']} 必需产物就绪)")
        return 0 if result["complete"] else 1

    steps = list(STEPS)
    if args.with_rootcause:
        steps += OPTIONAL_STEPS
    if args.with_tests:
        steps.append({"key": "unit_tests", "required": True, "cmd": TEST_CMD,
                      "desc": "统计/评测单测"})

    print(f"\n[run] 共 {len(steps)} 步")
    failed: dict[str, Any] | None = None
    for index, step in enumerate(steps, start=1):
        print(f"\n[{index}/{len(steps)}] {step['key']} — {step['desc']}")
        print(f"      $ {' '.join(step['cmd'])}")
        result = _run(step["cmd"])
        result["key"] = step["key"]
        result["required"] = step["required"]
        log.append(result)
        mark = "ok" if result["returncode"] == 0 else "FAIL"
        print(f"      [{mark}] rc={result['returncode']} ({result['elapsed_sec']}s)")
        if result["stdout_tail"]:
            for line in result["stdout_tail"].splitlines():
                print(f"        | {line}")
        if result["returncode"] != 0:
            if result["stderr_tail"]:
                for line in result["stderr_tail"].splitlines():
                    print(f"        ! {line}")
            if step["required"]:
                failed = result
                print(f"\n[stop] 必需步骤 `{step['key']}` 失败，复现中止。")
                break
            print(f"[warn] 可选步骤 `{step['key']}` 失败，继续。")

    # 2. 注册表
    reg = registry.write_registry()
    (out_dir / "reproduce-log.json").write_text(
        json.dumps({"started_at": datetime.now(timezone.utc).isoformat(),
                    "steps": log, "registry_complete": reg["complete"]},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n[registry] complete={reg['complete']} "
          f"({reg['n_present_required']}/{reg['n_required']} 必需产物就绪)")
    if reg["missing_required"]:
        print(f"[registry] 缺失：{', '.join(reg['missing_required'])}")
    print(f"[out] {out_dir / 'environment.json'}")
    print(f"[out] {out_dir / 'registry.json'}")
    print(f"[out] {out_dir / 'reproduce-log.json'}")

    if failed is not None:
        return 1
    if not reg["complete"]:
        return 1
    print("\n[done] 复现链完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

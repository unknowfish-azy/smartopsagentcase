"""采集复现所需的环境指纹（纯 stdlib）。

采集内容
--------
- Python 解释器：版本、实现、可执行文件路径（**不含**主机名/用户名，遵循隐私偏好）。
- 平台：系统、发行版、架构、CPU 核数、物理内存。
- 关键依赖版本：numpy / scipy / pytest（缺失记 ``null``，不报错）。
- Git：当前 commit、是否有未提交改动（dirty）。**dirty=True 时结果不可视为已归档复现**。
- 随机种子：统一定义，供 registry 与报告交叉核对。

用法：``python repro/environment.py`` 打印 JSON。
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]

# 所有评测/切分/重采样的统一种子（与 stats_inference / 各 eval 脚本保持一致）
SEEDS = {
    "split_controlled": 20261120,
    "stats_inference_bootstrap": 20261121,
    "eval_controlled_baseline": 20261121,
    "eval_inspector_ablation_controlled": 20261121,
    "ablation_rootcause": 20261120,
}


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True,
                             text=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def _total_memory_gb() -> float | None:
    if platform.system() == "Windows":
        try:
            import ctypes

            class _STATUSEX(ctypes.Structure):  # noqa: D401
                _fields_ = [("dwLength", ctypes.c_ulong),
                            ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            stat = _STATUSEX()
            stat.dwLength = ctypes.sizeof(_STATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):  # type: ignore[attr-defined]
                return round(stat.ullTotalPhys / 1024 ** 3, 2)
        except Exception:  # noqa: BLE001 - 仅诊断信息，失败就记 null
            return None
        return None
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                return round(int(line.split()[1]) / 1024 ** 2, 2)
    except OSError:
        return None
    return None


def _dependency_versions() -> dict[str, str | None]:
    """用 importlib.metadata 取版本（避免 import 触发的副作用与弃用告警）。"""
    from importlib import metadata

    versions: dict[str, str | None] = {}
    for name in ("numpy", "scipy", "pytest", "jsonschema", "httpx"):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def collect_environment() -> dict[str, Any]:
    commit = _git("rev-parse", "HEAD")
    dirty = _git("status", "--porcelain")
    return {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "python": {
            "version": sys.version.split()[0],
            "implementation": platform.python_implementation(),
            # 只记可执行文件名，不记绝对路径（路径会暴露用户名/目录结构）
            "executable_name": Path(sys.executable).name,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor() or None,
            "cpu_count": os.cpu_count(),
            "total_memory_gb": _total_memory_gb(),
        },
        "dependencies": _dependency_versions(),
        "git": {
            "commit": commit,
            "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": bool(dirty),
            "dirty_file_count": len(dirty.splitlines()) if dirty else 0,
            "note": "dirty=true 表示工作区有未提交改动，本结果不应视为已归档的复现状态",
        },
        "seeds": SEEDS,
    }


if __name__ == "__main__":
    print(json.dumps(collect_environment(), ensure_ascii=False, indent=2))

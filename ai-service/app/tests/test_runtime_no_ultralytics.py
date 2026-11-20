"""Z0-02：运行时不得引入 AGPL 检测器依赖。

这条测试守的不是"许可证好看"，而是一条可判定的边界：

    离线训练链可以依赖 AGPL（Ultralytics），
    但 ai-service 的运行时进程不许 import 它，也不许引用它的权重。

依据（2026-11-20 实测）：`ai-service/weights/yolo26n.pt` 与
`ai-service/yolov8n.pt` 的 checkpoint 元数据里都写着
`license=AGPL-3.0 (https://ultralytics.com/license)`。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]  # ai-service/app

#: 运行时真正会被加载的视觉/API 模块（不含离线训练脚本）
RUNTIME_MODULES = (
    "app.vision.classes",
    "app.vision.dataset",
    "app.vision.detector",
    "app.vision.screening",
    "app.vision.weak_label",
    "app.services.desktop_perceive",
)


def test_runtime_modules_do_not_import_ultralytics():
    for module in RUNTIME_MODULES:
        importlib.import_module(module)
        assert "ultralytics" not in sys.modules, (
            f"导入 {module} 时把 ultralytics 带进了运行时进程（AGPL-3.0）。"
            "检测器调用必须留在离线训练链里。"
        )


def test_runtime_never_references_agpl_weights():
    """运行时源码不许出现 AGPL 权重文件名。"""
    offenders: list[str] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        relative = path.relative_to(APP_ROOT)
        if relative.parts[0] == "tests":
            continue
        text = path.read_text(encoding="utf-8")
        if "yolo26n.pt" in text or "yolov8n.pt" in text:
            offenders.append(str(relative))
    assert offenders == [], (
        f"运行时源码引用了 AGPL 权重文件：{offenders}。"
        "若确实要在运行时做检测，先按 Z0-02 报告完成检测器替换。"
    )

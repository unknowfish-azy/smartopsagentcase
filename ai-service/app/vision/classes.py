"""YOLO 类别体系预设。

为什么做成"预设 + 可覆盖"而不是写死一份 classes：
1. 巡检异常类、机房设备类、通用 COCO 子集三套标签互不兼容，硬编码会让数据集不可迁移；
2. 换类别只改配置（或 `--classes-file`），不用改导出与训练脚本；
3. 类别名用 ASCII + 下划线，避免 ultralytics 写 `data.yaml` 时的编码问题。

顺序即 YOLO 的 class id（第一个为 0），改动顺序会让已标注的 label 文件失效——
所以新增类别只能往后追加。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# 三套预设：名称 → 有序类别列表（下标即 class id）
CLASS_PRESETS: dict[str, list[str]] = {
    # 巡检异常类：机器人巡检时真正要报警的语义
    "patrol_anomaly": [
        "person_intrusion",
        "obstacle",
        "fire_or_smoke",
        "missing_extinguisher",
        "fallen_equipment",
        "liquid_leak",
    ],
    # 机房/设备类：设备本体与部件，用于设备盘点与状态识别
    "datacenter_equipment": [
        "server",
        "rack",
        "status_led_abnormal",
        "cable",
        "gauge",
        "door_state",
    ],
    # 通用 COCO 子集：先用公开权重/公开数据跑通全链路，再替换成真实巡检类
    "coco_subset": [
        "person",
        "chair",
        "bottle",
        "laptop",
        "backpack",
        "fire_hydrant",
    ],
}

DEFAULT_PRESET = "coco_subset"


def preset_names() -> list[str]:
    return sorted(CLASS_PRESETS)


def resolve_classes(name_or_path: str | None) -> tuple[str, list[str]]:
    """把预设名或 JSON 文件解析成 (来源说明, 有序类别列表)。

    JSON 文件格式：`{"name": "my_set", "classes": ["a", "b"]}`，
    也接受纯数组 `["a", "b"]`（此时来源说明用文件名）。
    """
    if not name_or_path:
        return DEFAULT_PRESET, list(CLASS_PRESETS[DEFAULT_PRESET])

    candidate = Path(name_or_path)
    if candidate.exists() and candidate.is_file():
        raw: Any = json.loads(candidate.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            classes = raw.get("classes")
            name = str(raw.get("name") or candidate.stem)
        else:
            classes = raw
            name = candidate.stem
        _validate(classes, source=str(candidate))
        return name, list(classes)

    if name_or_path not in CLASS_PRESETS:
        raise ValueError(
            f"未知类别预设 {name_or_path!r}；可用预设：{', '.join(preset_names())}，"
            "或传一个 JSON 文件路径"
        )
    return name_or_path, list(CLASS_PRESETS[name_or_path])


def _validate(classes: Any, source: str) -> None:
    if not isinstance(classes, list) or not classes:
        raise ValueError(f"{source} 的 classes 必须是非空数组")
    seen: set[str] = set()
    for item in classes:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{source} 存在空的类别名")
        if item in seen:
            raise ValueError(f"{source} 存在重复类别 {item!r}（重复会让标注含义歧义）")
        seen.add(item)

"""VLM 弱标注候选：把多模态模型的框选结果转成 YOLO 候选标签。

为什么要这一步：标注是 YOLO 训练唯一的瓶颈。让 VLM 先粗框一遍，
人工从「画框」变成「改框/删框」，效率差好几倍。

三条边界（决定了本模块的形态）：
1. **只产候选，不产真值**：结果写到独立的 weak 目录，绝不覆盖 labels/；
   3B 级视觉模型的空间定位能力有限，坐标必须人工复核。
2. **解析要严**：模型会夹带解释文字、代码围栏、越界坐标、未知类别，
   一律按规则拒绝或裁剪，并把拒绝原因如实记账，不"修好"成看起来能用的框。
3. **纯函数**：prompt 构造与解析不做任何 IO，方便穷举边界用例。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

# 归一化坐标的下限：小于这个尺寸的框在 320~640 输入下几乎没有信息量
MIN_BOX_SIDE = 0.01

PROMPT_TEMPLATE = """你是机房巡检图像的标注助手。请只按下列类别框选画面中的目标：

{classes}

要求：
1. 只输出 JSON，不要输出任何解释文字；
2. 坐标用相对整图的归一化值（0~1），格式为中心点 + 宽高；
3. 必须逐个目标实测位置，**严禁照抄示例数值**；
4. 没有目标就返回空数组。

输出格式（尖括号是占位符，必须替换成你实测的 0~1 小数）：
{{"boxes": [{{"label": "类别名", "cx": <小数>, "cy": <小数>, "w": <小数>, "h": <小数>}}]}}
"""


@dataclass(frozen=True)
class CandidateBox:
    """一个归一化候选框。"""

    label: str
    cx: float
    cy: float
    w: float
    h: float


def build_prompt(class_names: Sequence[str]) -> str:
    """生成弱标注提示词。

    类别只列纯名称、不带序号：实测带 "0: name" 时 3B 模型会把序号一起
    抄进 label 字段（输出 "2: fire_or_smoke"）。类别到 id 的映射由代码完成，
    不需要模型知道序号。
    """
    listing = "\n".join(f"- {name}" for name in class_names)
    return PROMPT_TEMPLATE.format(classes=listing)


def extract_json_payload(text: str) -> Any:
    """从模型输出里抠出 JSON 主体。

    模型常见三种脏输出：整段包在 ```json 围栏里、JSON 前后带解释文字、
    直接返回裸数组。这里只做"截取+解析"，解析失败原样抛出由上层记账。
    """
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", cleaned, re.S)
    if fence:
        cleaned = fence.group(1).strip()

    start_candidates = [pos for pos in (cleaned.find("{"), cleaned.find("[")) if pos >= 0]
    if not start_candidates:
        raise ValueError("模型输出里没有 JSON")
    start = min(start_candidates)
    # 从后往前找配对的收尾符号：模型常在 JSON 后追加一句"以上是结果"
    end = max(cleaned.rfind("}"), cleaned.rfind("]"))
    if end <= start:
        raise ValueError("JSON 括号不完整")
    return json.loads(cleaned[start : end + 1])


def _iter_raw_boxes(payload: Any) -> list[dict[str, Any]]:
    """把三种可能的 JSON 形态归一成框列表。"""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        boxes = payload.get("boxes")
        if isinstance(boxes, list):
            return [item for item in boxes if isinstance(item, dict)]
        # 单个框直接作为对象返回的情况
        if "label" in payload:
            return [payload]
    return []


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _to_center_box(raw: dict[str, Any]) -> tuple[float, float, float, float] | None:
    """接受 cx/cy/w/h 或 x1/y1/x2/y2 两种写法，统一成中心点+宽高。"""
    if all(key in raw for key in ("cx", "cy", "w", "h")):
        try:
            return (
                _clamp01(float(raw["cx"])),
                _clamp01(float(raw["cy"])),
                _clamp01(float(raw["w"])),
                _clamp01(float(raw["h"])),
            )
        except (TypeError, ValueError):
            return None
    if all(key in raw for key in ("x1", "y1", "x2", "y2")):
        try:
            x1, y1 = _clamp01(float(raw["x1"])), _clamp01(float(raw["y1"]))
            x2, y2 = _clamp01(float(raw["x2"])), _clamp01(float(raw["y2"]))
        except (TypeError, ValueError):
            return None
        left, right = min(x1, x2), max(x1, x2)
        top, bottom = min(y1, y2), max(y1, y2)
        return ((left + right) / 2, (top + bottom) / 2, right - left, bottom - top)
    return None


def normalize_label(raw_label: str, class_names: Sequence[str]) -> str:
    """把模型输出的类别名对齐到 data.yaml 的规范写法。

    只做格式归一（去掉 "2:" 这类序号前缀、大小写、空白），不做语义猜测：
    归一后仍不在清单里的，一律按未知类别拒绝。
    """
    cleaned = re.sub(r"^\s*\d+\s*[:.)、]\s*", "", raw_label.strip())
    cleaned = cleaned.strip().strip("'\"`.,;")
    by_lower = {name.lower(): name for name in class_names}
    return by_lower.get(cleaned.lower(), cleaned)


def parse_candidates(
    text: str, class_names: Sequence[str]
) -> tuple[list[CandidateBox], list[str]]:
    """解析模型输出。

    @return (通过的候选框, 拒绝原因列表)。拒绝原因逐条可读，
            用于人工复核时判断"是模型没看见"还是"解析被我拦掉了"。
    """
    try:
        payload = extract_json_payload(text)
    except (ValueError, json.JSONDecodeError) as error:
        return [], [f"JSON 解析失败：{error}"]

    accepted: list[CandidateBox] = []
    rejected: list[str] = []
    for raw in _iter_raw_boxes(payload):
        label = normalize_label(str(raw.get("label") or raw.get("name") or ""), class_names)
        if label not in class_names:
            rejected.append(f"未知类别 {label!r}")
            continue
        geometry = _to_center_box(raw)
        if geometry is None:
            rejected.append(f"{label}: 缺少有效坐标字段")
            continue
        cx, cy, w, h = geometry
        if w < MIN_BOX_SIDE or h < MIN_BOX_SIDE:
            rejected.append(f"{label}: 框尺寸过小 ({w:.3f}×{h:.3f})")
            continue
        # 越界裁剪到画布内，避免训练时 ultralytics 直接丢弃整行
        left, top = cx - w / 2, cy - h / 2
        right, bottom = cx + w / 2, cy + h / 2
        left, right = max(0.0, left), min(1.0, right)
        top, bottom = max(0.0, top), min(1.0, bottom)
        if right - left < MIN_BOX_SIDE or bottom - top < MIN_BOX_SIDE:
            rejected.append(f"{label}: 裁剪后无有效面积")
            continue
        accepted.append(
            CandidateBox(
                label=label,
                cx=round((left + right) / 2, 6),
                cy=round((top + bottom) / 2, 6),
                w=round(right - left, 6),
                h=round(bottom - top, 6),
            )
        )
    return accepted, rejected


def format_yolo_line(box: CandidateBox, class_names: Sequence[str]) -> str:
    """转成 YOLO 行：`class_id cx cy w h`。类别不在清单里直接抛错，不静默取 0。"""
    try:
        class_id = list(class_names).index(box.label)
    except ValueError as error:
        raise ValueError(f"类别 {box.label!r} 不在 data.yaml 的 names 里") from error
    return f"{class_id} {box.cx:.6f} {box.cy:.6f} {box.w:.6f} {box.h:.6f}"


def degenerate_signatures(
    boxes_by_image: dict[str, Sequence[CandidateBox]], min_images: int = 2
) -> set[tuple[str, float, float, float, float]]:
    """找出「跨图逐位相同」的框签名，判定为模型复读模板而非真实定位。

    为什么需要这条：实测 qwen2.5vl:3b 在两张完全不同的图上吐出
    `fire_or_smoke, 0.3, 0.4, 0.2, 0.2` 这种逐位一致的坐标。
    真实推理不可能在小数第 6 位完全一致，所以按"完全相等"判伪足够安全，
    不会误杀固定机位下真实存在但位置稳定的目标。

    @param boxes_by_image 图片标识 → 该图的候选框
    @param min_images 至少出现在多少张不同图片上才判伪
    """
    seen: dict[tuple[str, float, float, float, float], set[str]] = {}
    for image, boxes in boxes_by_image.items():
        for box in boxes:
            signature = (box.label, box.cx, box.cy, box.w, box.h)
            seen.setdefault(signature, set()).add(image)
    return {signature for signature, images in seen.items() if len(images) >= min_images}


def merge_candidate_lines(
    existing_text: str,
    candidate_text: str,
    allowed_ids: set[int],
) -> tuple[str, int, list[str]]:
    """把候选里白名单类别的行并进已有 label。

    为什么按类别白名单而不是全量回写：实测 GroundingDINO 在 `fire_or_smoke`
    上 7/8 命中且正常帧零误报，但 `missing_extinguisher` / `fallen_equipment`
    会把服务器本体框成"缺失灭火器"，属于系统性误检。全量回写等于把误检
    钉进真值，后面只能靠人工一条条删。

    只追加不覆盖：人工已标的行原样保留；逐位相同的行跳过，重复执行幂等。

    @return (合并后的文本, 新增行数, 跳过原因列表)
    """
    merged: list[str] = []
    seen: set[tuple[str, ...]] = set()
    for raw in existing_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        merged.append(line)
        # 已存在行按"字段逐位相同"去重，不做数值容差：容差会让相邻帧的
        # 同名框互相吞掉，而这里的目的只是防重复执行
        seen.add(tuple(line.split()))

    added = 0
    skipped: list[str] = []
    for raw in candidate_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        fields = line.split()
        try:
            class_id = int(fields[0])
        except (ValueError, IndexError):
            skipped.append(f"非法行 {line!r}")
            continue
        if class_id not in allowed_ids:
            continue  # 白名单外的类别按设计静默跳过，不算异常
        key = tuple(fields)
        if key in seen:
            skipped.append(f"重复行 {line!r}")
            continue
        seen.add(key)
        merged.append(line)
        added += 1

    text = "\n".join(merged) + "\n" if merged else ""
    return text, added, skipped


def load_class_names(data_yaml: Path | str) -> list[str]:
    """从 data.yaml 读 names。

    只支持本项目 `write_yolo_dataset` 产出的两种写法（`name: idx` 映射与 `- name` 列表），
    为此不引入 PyYAML —— 与 app/vision/dataset.py 的取舍保持一致。
    """
    path = Path(data_yaml)
    lines = path.read_text(encoding="utf-8").splitlines()
    names: dict[int, str] = {}
    listed: list[str] = []
    in_names = False
    for raw in lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if re.match(r"^names\s*:", raw):
            in_names = True
            continue
        if not in_names:
            continue
        if raw.startswith((" ", "\t")):
            mapping = re.match(r"^\s+(\d+)\s*:\s*(.+?)\s*$", raw)
            if mapping:
                names[int(mapping.group(1))] = mapping.group(2).strip().strip("'\"")
                continue
            item = re.match(r"^\s*-\s*(.+?)\s*$", raw)
            if item:
                listed.append(item.group(1).strip().strip("'\""))
            continue
        # 顶格的新键表示 names 段结束
        in_names = False

    if names:
        return [names[index] for index in sorted(names)]
    return listed

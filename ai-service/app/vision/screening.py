"""VLM 二分类筛图：判断一帧里有没有值得人工标注的目标。

为什么在弱标注之外还要这一步：
- 实测 `qwen2.5vl:3b` 能描述画面（"四台服务器、绿黄指示灯"）但出不了准框，
  坐标精度不够且跨图复读 → 框只能当参考，人工仍要逐张核对，省不下来；
- 但"有没有异常目标"是二分类，比回归坐标简单一个数量级，3B 模型够用；
- 人工标注的真正瓶颈是"在几千张正常帧里找那几十张有异常的"，
  筛图把这一步从「逐张看」变成「只看候选」。

三条边界（决定了本模块的形态）：
1. **只筛不标**：不写任何 label 文件，产物是给人看的图清单与判定明细；
2. **三态而非二态**：yes / no / uncertain。模型说不清的一律进 uncertain，
   绝不把"看不懂"折叠成 no —— 那等于把漏检伪装成"画面干净"；
3. **必须自证判别力**：yes 率贴着 0% 或 100% 时模型没有区分能力，
   报告要显式判为"这批结果不能当筛图依据"，而不是照单全收当地面真值。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Sequence

from app.vision.weak_label import extract_json_payload, normalize_label

# 提示词刻意只问"有没有"，绝口不提坐标：
# 一旦让它报位置，就会退化回弱标注那条已被证伪的路（坐标靠猜、跨图复读）。
SCREEN_PROMPT_TEMPLATE = """你是机房巡检图像的初筛助手。请判断这张图里是否存在下列任一目标：

{classes}

要求：
1. 只输出 JSON，不要输出解释文字；
2. has_target 只能是 true 或 false；
3. 若 has_target 为 true，在 labels 里列出命中的类别名，必须来自上面的清单，原样照抄；
4. 若画面里没有上述目标，has_target 填 false，labels 给空数组；
5. confidence 填你对本次判断的把握（0~1 的小数）。

输出格式：
{{"has_target": false, "labels": [], "confidence": 0.9, "reason": "一句话依据"}}
"""

# 判别力自检：样本量低于这个数时，比例没有统计意义，不做判定
MIN_DISCRIMINATION_SAMPLES = 10
# yes 率高于/低于这两个阈值即可认为模型在恒定输出，而不是在区分
HIGH_YES_RATE = 0.95
LOW_YES_RATE = 0.05
MAX_REASON_CHARS = 200

_TRUE_WORDS = {"true", "yes", "y", "1", "是", "有", "存在"}
_FALSE_WORDS = {"false", "no", "n", "0", "否", "无", "没有", "不存在"}


@dataclass(frozen=True)
class ScreenVerdict:
    """一帧的筛图结论。

    decision 取值：
    - `yes`       有目标且类别合法 → 进人工标注队列
    - `no`        明确没有 → 不标（可抽检）
    - `uncertain` 模型说不清 / 说了有但类别非法 / 输出不可解析 → 必须人工看
    """

    decision: str
    labels: tuple[str, ...] = ()
    confidence: float | None = None
    reason: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)


def build_screen_prompt(class_names: Sequence[str]) -> str:
    """生成筛图提示词。类别同样只列纯名称，避免模型把序号抄进 labels。"""
    listing = "\n".join(f"- {name}" for name in class_names)
    return SCREEN_PROMPT_TEMPLATE.format(classes=listing)


def _as_boolish(value: Any) -> bool | None:
    """把模型五花八门的布尔写法归一；无法判定时返回 None（由上层进 uncertain）。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
        return None
    if isinstance(value, str):
        token = value.strip().lower()
        if token in _TRUE_WORDS:
            return True
        if token in _FALSE_WORDS:
            return False
    return None


def _as_confidence(value: Any) -> float | None:
    """置信度只做范围裁剪；缺失或非数值时返回 None，绝不默认成 1.0。"""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(max(0.0, min(1.0, number)), 4)


def _as_label_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def _uncertain(reason: str, confidence: float | None = None, extra: Sequence[str] = ()) -> ScreenVerdict:
    return ScreenVerdict(
        decision="uncertain",
        confidence=confidence,
        notes=tuple(extra) + (reason,),
    )


def parse_screen_result(text: str, class_names: Sequence[str]) -> ScreenVerdict:
    """解析筛图输出。

    关键取舍：`has_target=true` 但给不出合法类别时判 `uncertain` 而非 `yes` 或 `no`。
    判 yes 会把一堆噪音塞进人工队列（而且没有任何类别可用），判 no 会漏检，
    只有 uncertain 既保留"模型觉得有东西"的信号，又不会污染统计。
    """
    try:
        payload = extract_json_payload(text)
    except (ValueError, json.JSONDecodeError) as error:
        return _uncertain(f"JSON 解析失败：{error}")

    # 少数情况下模型直接吐 true/false
    if not isinstance(payload, dict):
        flag = _as_boolish(payload)
        if flag is None:
            return _uncertain("输出不是 JSON 对象")
        return _uncertain("模型只回答了有无，未给出类别") if flag else ScreenVerdict("no")

    flag = _as_boolish(
        payload.get("has_target", payload.get("has_anomaly", payload.get("yes")))
    )
    if flag is None:
        return _uncertain("缺少可判定的 has_target 字段")

    confidence = _as_confidence(payload.get("confidence"))
    reason_raw = payload.get("reason") or payload.get("explanation") or ""
    reason = str(reason_raw).strip().replace("\n", " ")[:MAX_REASON_CHARS]

    if not flag:
        # 说"没有"时不采信 labels：模型常在这种情况把类别清单又抄一遍
        return ScreenVerdict(decision="no", confidence=confidence, reason=reason)

    accepted: list[str] = []
    rejected: list[str] = []
    for item in _as_label_list(
        payload.get("labels") or payload.get("targets") or payload.get("classes")
    ):
        name = normalize_label(str(item), class_names)
        if name in class_names:
            if name not in accepted:
                accepted.append(name)
        else:
            rejected.append(f"未知类别 {name!r}")

    if not accepted:
        problem = "判定为有目标但未给出合法类别"
        return _uncertain(problem, confidence, rejected)

    return ScreenVerdict(
        decision="yes",
        labels=tuple(accepted),
        confidence=confidence,
        reason=reason,
        notes=tuple(rejected),
    )


def summarize(decisions: Sequence[str], failed: int = 0) -> dict[str, Any]:
    """汇总判定分布并自检判别力。

    yes 率的分母是"模型真正表态"的帧（yes + no），uncertain 与调用失败都不算表态：
    把 uncertain 记作 no 会虚低命中率，记作 yes 会虚高，两种都会误导人工排期。
    """
    total_verdicts = len(decisions)
    yes = decisions.count("yes")
    no = decisions.count("no")
    uncertain = decisions.count("uncertain")
    decided = yes + no
    yes_rate = round(yes / decided, 4) if decided else 0.0

    low_discrimination = decided >= MIN_DISCRIMINATION_SAMPLES and (
        yes_rate >= HIGH_YES_RATE or yes_rate <= LOW_YES_RATE
    )
    warning = ""
    if low_discrimination:
        warning = (
            f"yes 率 {yes_rate:.1%}（{yes}/{decided}），接近恒定输出："
            "该模型在这批图上没有展示区分能力，本批结果不能作为筛图依据"
        )

    return {
        "frames": total_verdicts + failed,
        "decided": decided,
        "yes": yes,
        "no": no,
        "uncertain": uncertain,
        "failed": failed,
        "yes_rate": yes_rate,
        "low_discrimination": low_discrimination,
        "warning": warning,
    }

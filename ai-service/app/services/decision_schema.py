"""DS-04 判定输出契约：唯一的 JSON Schema。

Ollama 走 `format`，OpenAI 兼容端点走 `response_format`，护栏与蒸馏筛共用同一份。
字段是 ARCHITECTURE §3.2 契约的超集：保留 verdict，同时保留 evidenceOutput 侧的
label / confidence，避免训练数据与推理契约两套形状。
"""

from __future__ import annotations

import json
from typing import Any

VERDICTS = (
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "UNSUPPORTED",
    "CONTRADICTED",
    "INSUFFICIENT",
)
LABELS = ("SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "CONTRADICTED")
PROBE_DECISIONS = ("SELECTED", "WAIT", "STOP")

DECISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["verdict", "used_refs", "gaps_acknowledged", "next_probe", "rationale"],
    "properties": {
        "verdict": {"type": "string", "enum": list(VERDICTS)},
        # label 与 verdict 同源，null 表示「不给出正向标签」（缺口场景）。
        "label": {"type": ["string", "null"], "enum": [*LABELS, None]},
        "used_refs": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "gaps_acknowledged": {"type": "array", "items": {"type": "string"}},
        "next_probe": {
            "type": "object",
            "required": ["decision", "reason"],
            "properties": {
                "decision": {"type": "string", "enum": list(PROBE_DECISIONS)},
                "probe_id": {"type": ["string", "null"]},
                "reason": {"type": "string", "maxLength": 200},
            },
            "additionalProperties": False,
        },
        "rationale": {"type": "string", "maxLength": 240},
    },
    "additionalProperties": False,
}


def schema_json() -> str:
    """便于 CLI / 提示词内嵌的紧凑序列化。"""
    return json.dumps(DECISION_SCHEMA, ensure_ascii=False, separators=(",", ":"))

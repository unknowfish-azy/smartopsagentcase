"""训练数据落湖（D1）：把运行时数据规整成可复用样本。

三条原则：
1. 纯函数只做字段规整、不做 I/O，方便 pytest 直测；
2. 落盘按「日分区 + 固定文件名」覆盖写，重跑幂等（不会重复堆文件）；
3. 不推断缺失字段：轨迹里没有任务原文就不编造 prompt，等标注阶段补。

字段口径来自现有表结构（已核对生产库）：
- sentinel_metric_sample：task_id / sampled_at / metric / value_num / value_text / abnormal
- inspector_event + inspection_evidence：核查结论与证据分表
- agent_decision_loop：症状 → 分析 → 决策 → 结果 → 教训 的完整决策链
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

# 轨迹字段：来自 agent/executor/executor.py 的 terminal event
TRAJECTORY_FIELDS = (
    "request_id",
    "task_id",
    "run_id",
    "step_id",
    "status",
    "error_class",
    "component",
    "ts",
)

# 指标字段：与 sentinel_metric_sample 表列名一致
METRIC_FIELDS = ("task_id", "metric", "value_num", "value_text", "abnormal")


def _day_of(timestamp: Any, label: str) -> str:
    """统一取日分区键；缺失直接报错，不产出无法按时间切分的数据集。"""
    if timestamp is None:
        raise ValueError(f"{label} 缺失，无法按日分区")
    if hasattr(timestamp, "strftime"):
        return timestamp.strftime("%Y-%m-%d")
    return str(timestamp)[:10]


def _parse_json(raw: Any) -> Any:
    """JSON 列容错解析：解析失败保留原文，避免整批导出因一行坏数据中断。"""
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def normalize_metric_sample(row: dict[str, Any]) -> dict[str, Any]:
    """把一条 sentinel 指标采样规整成数据湖记录。

    保留 task_id 是刻意的：指标要能按采集任务切分训练/评测，
    否则同一任务的相邻采样会同时出现在两侧，造成评测虚高。
    """
    record: dict[str, Any] = {field: row.get(field) for field in METRIC_FIELDS}
    record["abnormal"] = int(row.get("abnormal") or 0)
    record["dt"] = _day_of(row.get("sampled_at"), "sampled_at")
    record["sampled_at"] = str(row.get("sampled_at"))
    return record


def normalize_terminal_event(event: dict[str, Any]) -> dict[str, Any]:
    """把执行器 terminal event 规整成轨迹记录。

    status 是唯一强约束字段：没有它就无法区分成功/失败轨迹，样本不可用。
    error_class 兼容两种来源（error_category / error_class），避免导出时丢归因。
    """
    status = event.get("status")
    if not status:
        raise ValueError("terminal event 缺少 status，无法判定轨迹可用性")

    return {
        "request_id": event.get("request_id"),
        "task_id": event.get("task_id"),
        "run_id": event.get("run_id"),
        "step_id": event.get("step_id"),
        "status": status,
        "error_class": event.get("error_category") or event.get("error_class"),
        "component": event.get("component"),
        "ts": event.get("ts") or event.get("timestamp"),
    }


def normalize_inspector_row(
    row: dict[str, Any], evidence_count: int = 0
) -> dict[str, Any]:
    """把 inspector_event（+证据计数）规整成「标注候选」。

    保留 agent_claim / reason / recommendation 原文而不做改写：
    核查记录是弱标注来源，人工复核时需要看到原始判断。
    """
    return {
        "inspection_id": row.get("id"),
        "task_id": row.get("task_id"),
        "target": row.get("target"),
        "status": row.get("status"),
        "severity": row.get("severity"),
        "category": row.get("category"),
        "agent_claim": row.get("agent_claim"),
        "reason": row.get("reason"),
        "recommendation": row.get("recommendation"),
        "requires_human": bool(row.get("requires_human")),
        "evidence_count": int(evidence_count or 0),
        "metadata": _parse_json(row.get("metadata_json")) or {},
        "created_at": str(row.get("created_at") or ""),
    }


def normalize_decision_row(row: dict[str, Any]) -> dict[str, Any]:
    """把 agent_decision_loop 规整成决策链样本。

    这是最有价值的样本来源：症状、分析、证据、决策、结果、教训齐全，
    可直接作为 SFT 的目标输出（prompt 侧等标注阶段拼装，这里不编造）。
    """
    evidence = _parse_json(row.get("evidence_json")) or []
    return {
        "decision_id": row.get("id"),
        "incident_key": row.get("incident_key"),
        "title": row.get("title"),
        "source_type": row.get("source_type"),
        "stage": row.get("stage"),
        "severity": row.get("severity"),
        "symptom": row.get("symptom"),
        "analysis": row.get("analysis"),
        "evidence_count": len(evidence) if isinstance(evidence, list) else 0,
        "recommendation": row.get("recommendation"),
        "decision": row.get("decision"),
        "decision_basis": row.get("decision_basis"),
        "requires_human": bool(row.get("requires_human")),
        "outcome": row.get("outcome"),
        "lesson": row.get("lesson"),
        "confidence": row.get("confidence"),
        "reviewed": row.get("reviewed_at") is not None,
        "created_at": str(row.get("created_at") or ""),
    }


def write_jsonl(records: Iterable[dict[str, Any]], path: Path | str) -> str:
    """写 JSONL（覆盖写，保证重跑幂等），返回「路径（行数）」摘要。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with target.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return f"{target} ({count} 行)"


def write_metrics_parquet(
    records: list[dict[str, Any]], out_dir: Path | str
) -> list[str]:
    """按 dt 分区写 Parquet，每天一个固定文件名，重跑覆盖。"""
    if not records:
        return []

    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq

    frame = pd.DataFrame(records)
    written: list[str] = []
    for day, chunk in frame.groupby("dt", sort=True):
        target_dir = Path(out_dir) / f"dt={day}"
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / "metrics.parquet"
        pq.write_table(pa.Table.from_pandas(chunk, preserve_index=False), file_path)
        written.append(str(file_path))
    return written

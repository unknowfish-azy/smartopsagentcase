"""D1 数据落湖纯函数测试：字段规整、分区、幂等覆盖、坏数据拦截。"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from app.training.dataset import (
    normalize_decision_row,
    normalize_inspector_row,
    normalize_metric_sample,
    normalize_terminal_event,
    write_jsonl,
    write_metrics_parquet,
)


def test_normalize_metric_sample_补日分区并保留任务归属():
    row = {
        "task_id": 7,
        "sampled_at": datetime(2026, 11, 17, 8, 30),
        "metric": "cpu.usage",
        "value_num": 12.5,
        "value_text": None,
        "abnormal": 0,
    }
    record = normalize_metric_sample(row)

    assert record["dt"] == "2026-11-17"
    assert record["metric"] == "cpu.usage"
    assert record["value_num"] == 12.5
    assert record["task_id"] == 7
    assert record["abnormal"] == 0
    assert record["sampled_at"].startswith("2026-11-17")

    with pytest.raises(ValueError):
        normalize_metric_sample({**row, "sampled_at": None})


def test_normalize_minimal_abnormal_取整容错():
    record = normalize_metric_sample(
        {"sampled_at": "2026-11-17 08:00:00", "metric": "m", "abnormal": None}
    )
    assert record["abnormal"] == 0


def test_normalize_terminal_event_保留失败归因():
    event = {
        "request_id": "req-1",
        "task_id": "task-1",
        "run_id": "run-1",
        "step_id": "step-2",
        "status": "failed",
        "error_category": "TIMEOUT",
        "component": "executor",
    }
    record = normalize_terminal_event(event)

    assert record["status"] == "failed"
    assert record["error_class"] == "TIMEOUT"
    assert normalize_terminal_event(
        {**event, "error_category": None, "error_class": "RATE_LIMIT"}
    )["error_class"] == "RATE_LIMIT"

    with pytest.raises(ValueError):
        normalize_terminal_event({"request_id": "req-2"})


def test_normalize_inspector_row_解析元数据且坏JSON不中断():
    row = {
        "id": "insp-1",
        "task_id": "task-1",
        "target": "demo-server-001",
        "status": "DONE",
        "severity": "HIGH",
        "category": "CAPACITY",
        "agent_claim": "磁盘将在 3 天内写满",
        "reason": "最近 7 天增长率 4.2%/天",
        "recommendation": "清理 /var/log 并扩容",
        "requires_human": 1,
        "metadata_json": '{"planner": "llm"}',
        "created_at": "2026-11-17 08:00:00",
    }
    record = normalize_inspector_row(row, evidence_count=2)

    assert record["evidence_count"] == 2
    assert record["requires_human"] is True
    assert record["metadata"] == {"planner": "llm"}

    broken = normalize_inspector_row({**row, "metadata_json": "{not-json"})
    assert broken["metadata"] == {"raw": "{not-json"}
    assert normalize_inspector_row({})["evidence_count"] == 0


def test_normalize_decision_row_统计证据并标记已复核():
    row = {
        "id": "dec-1",
        "incident_key": "disk-full",
        "title": "磁盘写满",
        "symptom": "写入失败",
        "analysis": "日志未轮转",
        "evidence_json": '[{"source":"metric"},{"source":"log"}]',
        "decision": "清理并扩容",
        "outcome": "resolved",
        "confidence": 0.82,
        "reviewed_at": "2026-11-17 09:00:00",
        "created_at": "2026-11-17 08:00:00",
    }
    record = normalize_decision_row(row)

    assert record["evidence_count"] == 2
    assert record["reviewed"] is True
    assert record["confidence"] == 0.82
    # 未复核 + 证据字段缺失
    fallback = normalize_decision_row({"id": "dec-2"})
    assert fallback["reviewed"] is False
    assert fallback["evidence_count"] == 0


def test_write_jsonl_覆盖写幂等(tmp_path):
    first = write_jsonl([{"a": 1}, {"b": "中文"}], tmp_path / "sub" / "x.jsonl")
    second = write_jsonl([{"c": 3}], tmp_path / "sub" / "x.jsonl")

    assert "2 行" in first and "1 行" in second
    lines = (tmp_path / "sub" / "x.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert lines == [json.dumps({"c": 3}, ensure_ascii=False)]


def test_write_metrics_parquet_按日分区且重跑覆盖(tmp_path):
    records = [
        normalize_metric_sample(
            {"task_id": 1, "metric": "cpu", "value_num": 1.0, "sampled_at": datetime(2026, 11, 16, 23, 59)}
        ),
        normalize_metric_sample(
            {"task_id": 1, "metric": "cpu", "value_num": 2.0, "sampled_at": datetime(2026, 11, 17, 0, 1)}
        ),
    ]
    files = write_metrics_parquet(records, tmp_path)
    assert len(files) == 2
    assert (tmp_path / "dt=2026-11-16" / "metrics.parquet").exists()

    write_metrics_parquet(records[:1], tmp_path)
    import pyarrow.parquet as pq

    table = pq.read_table(tmp_path / "dt=2026-11-16" / "metrics.parquet")
    assert table.num_rows == 1
    assert write_metrics_parquet([], tmp_path) == []

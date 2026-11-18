"""Agent 执行事件持久化（P0-2 修复）。

把 executor 的 terminal event 写入数据库，让执行轨迹可事后查询、可做 SFT 数据回流。

设计原则（同 training_ledger.py）：
* **best-effort**：数据库不可用时降级为写本地 JSONL，绝不阻塞执行链路。
* **零强依赖**：不强制安装 pymysql。
* **不存敏感数据**：只存关联 ID（request_id/run_id/step_id）+ 状态 + 工具名 + 错误分类，
  不存 payload、credentials、prompt、output。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# JSONL 兜底目录
_EVENT_DIR = Path(__file__).resolve().parents[2] / "data" / "agent_events"
_EVENT_DIR.mkdir(parents=True, exist_ok=True)


def _db_config() -> dict[str, Any]:
    return {
        "host": os.environ.get("MYSQL_HOST", "localhost"),
        "port": int(os.environ.get("MYSQL_PORT", "3306")),
        "user": os.environ.get("MYSQL_USERNAME", "root"),
        "password": os.environ.get("MYSQL_PASSWORD", "root"),
        "database": os.environ.get("MYSQL_DATABASE", "smartops"),
    }


def _mysql_available() -> bool:
    try:
        import pymysql  # type: ignore
    except ImportError:
        return False
    cfg = _db_config()
    try:
        conn = pymysql.connect(
            host=cfg["host"], port=cfg["port"], user=cfg["user"],
            password=cfg["password"], database=cfg["database"],
            connect_timeout=3,
        )
        conn.close()
        return True
    except Exception:
        return False


def _write_jsonl(record: dict[str, Any]) -> None:
    record = dict(record)
    record["_storage"] = "jsonl"
    record["_written_at"] = datetime.now(timezone.utc).isoformat()
    path = _EVENT_DIR / "execution_events.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _execute_mysql(sql: str, params: tuple = ()) -> bool:
    try:
        import pymysql  # type: ignore
    except ImportError:
        return False
    cfg = _db_config()
    try:
        conn = pymysql.connect(
            host=cfg["host"], port=cfg["port"], user=cfg["user"],
            password=cfg["password"], database=cfg["database"],
            connect_timeout=5,
        )
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception:
        return False


def persist_execution_event(
    *,
    event: dict[str, Any],
    tool_name: str | None = None,
    error_category: str | None = None,
    failure_class: str | None = None,
    duration_ms: int | None = None,
) -> bool:
    """持久化一条 executor terminal event。

    返回 True 表示写入 MySQL，False 表示降级 JSONL。
    任何异常都被吞掉——持久化失败不能影响执行链路。
    """
    sql = """
        INSERT INTO agent_execution_event
            (event_id, request_id, task_id, run_id, step_id, source, status,
             tool_name, error_category, failure_class, duration_ms)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            status = VALUES(status),
            tool_name = VALUES(tool_name),
            error_category = VALUES(error_category),
            failure_class = VALUES(failure_class),
            duration_ms = VALUES(duration_ms)
    """
    record = {
        "event_id": event.get("event_id"),
        "request_id": event.get("request_id"),
        "task_id": event.get("task_id"),
        "run_id": event.get("run_id"),
        "step_id": event.get("step_id"),
        "source": event.get("source"),
        "status": event.get("status"),
        "tool_name": tool_name,
        "error_category": error_category,
        "failure_class": failure_class,
        "duration_ms": duration_ms,
    }
    ok = _execute_mysql(sql, (
        record["event_id"], record["request_id"], record["task_id"],
        record["run_id"], record["step_id"], record["source"],
        record["status"], tool_name, error_category, failure_class, duration_ms,
    ))
    if not ok:
        _write_jsonl(record)
    return ok


def event_persistence_status() -> dict[str, Any]:
    """返回持久化状态，供体检脚本调用。"""
    mysql_ok = _mysql_available()
    jsonl_path = _EVENT_DIR / "execution_events.jsonl"
    jsonl_count = 0
    if jsonl_path.exists():
        with jsonl_path.open(encoding="utf-8") as f:
            jsonl_count = sum(1 for _ in f)
    return {
        "mysql_available": mysql_ok,
        "jsonl_fallback_dir": str(_EVENT_DIR),
        "jsonl_event_count": jsonl_count,
    }

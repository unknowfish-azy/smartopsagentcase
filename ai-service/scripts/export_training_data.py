"""D1 数据导出脚本：把运行时数据落成可复用样本。

用法（在 ai-service 目录下执行）：

    python scripts/export_training_data.py metrics     --out ../data/lake/metrics --since 2026-11-01
    python scripts/export_training_data.py decisions   --out ../data/lake/decisions
    python scripts/export_training_data.py inspections --out ../data/lake/inspections
    python scripts/export_training_data.py trajectories --input logs/run_events.jsonl --out ../data/lake/trajectories

说明：
- 指标来自 sentinel_metric_sample（server_metric 目前为空，真实采样在 sentinel 侧）；
- 决策链来自 agent_decision_loop，核查来自 inspector_event + inspection_evidence；
- 执行器事件目前只在运行期产生、未落库，因此从 JSONL 文件导入；
- 输出全部覆盖写，重跑幂等。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.training.dataset import (  # noqa: E402
    normalize_decision_row,
    normalize_inspector_row,
    normalize_metric_sample,
    normalize_terminal_event,
    write_jsonl,
    write_metrics_parquet,
)

METRIC_SQL = """
SELECT task_id, sampled_at, metric, value_num, value_text, abnormal
FROM sentinel_metric_sample
WHERE (%(since)s IS NULL OR sampled_at >= %(since)s)
  AND (%(until)s IS NULL OR sampled_at < %(until)s)
ORDER BY sampled_at
LIMIT %(limit)s
"""

# 证据分表，用相关子查询取计数：核查事件与证据是 1:N
INSPECTION_SQL = """
SELECT e.id, e.task_id, e.target, e.status, e.severity, e.category,
       e.agent_claim, e.reason, e.recommendation, e.requires_human,
       e.metadata_json, e.created_at,
       (SELECT COUNT(*) FROM inspection_evidence v WHERE v.event_id = e.id) AS evidence_count
FROM inspector_event e
ORDER BY e.created_at
LIMIT %(limit)s
"""

DECISION_SQL = """
SELECT id, incident_key, title, source_type, stage, severity,
       symptom, analysis, evidence_json, recommendation, decision, decision_basis,
       requires_human, outcome, lesson, confidence, reviewed_at, created_at
FROM agent_decision_loop
ORDER BY created_at
LIMIT %(limit)s
"""


def _db_config() -> dict[str, Any]:
    """数据库连接：优先 SMARTOPS_DB_*，回退后端沿用的 MYSQL_*。"""
    return {
        "host": os.getenv("SMARTOPS_DB_HOST") or os.getenv("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.getenv("SMARTOPS_DB_PORT") or os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("SMARTOPS_DB_USER") or os.getenv("MYSQL_USERNAME", "root"),
        "password": os.getenv("SMARTOPS_DB_PASSWORD") or os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("SMARTOPS_DB_NAME") or os.getenv("MYSQL_DATABASE", "smartops"),
    }


def _fetch(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    import pymysql

    connection = pymysql.connect(cursorclass=pymysql.cursors.DictCursor, **_db_config())
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return list(cursor.fetchall())
    finally:
        connection.close()


def _read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path} 第 {lineno} 行不是合法 JSON：{error}") from error


def export_metrics(args: argparse.Namespace) -> None:
    rows = _fetch(METRIC_SQL, {"since": args.since, "until": args.until, "limit": args.limit})
    records = [normalize_metric_sample(row) for row in rows]
    files = write_metrics_parquet(records, args.out)
    print(f"指标 {len(records)} 行 → {len(files)} 个分区文件，输出目录 {args.out}")


def export_decisions(args: argparse.Namespace) -> None:
    rows = _fetch(DECISION_SQL, {"limit": args.limit})
    records = [normalize_decision_row(row) for row in rows]
    result = write_jsonl(records, Path(args.out) / "decisions.jsonl")
    print(f"决策链 {len(records)} 条 → {result}")


def export_inspections(args: argparse.Namespace) -> None:
    rows = _fetch(INSPECTION_SQL, {"limit": args.limit})
    records = [
        normalize_inspector_row(row, evidence_count=row.get("evidence_count") or 0)
        for row in rows
    ]
    result = write_jsonl(records, Path(args.out) / "inspections.jsonl")
    print(f"核查记录 {len(records)} 条 → {result}")


def export_trajectories(args: argparse.Namespace) -> None:
    records = []
    skipped = 0
    for event in _read_jsonl(Path(args.input)):
        try:
            records.append(normalize_terminal_event(event))
        except ValueError:
            skipped += 1
    result = write_jsonl(records, Path(args.out) / "trajectories.jsonl")
    print(f"轨迹 {len(records)} 条（跳过 {skipped} 条无 status）→ {result}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="D1 训练数据导出")
    sub = parser.add_subparsers(dest="command", required=True)

    metrics = sub.add_parser("metrics", help="sentinel_metric_sample → Parquet（按日分区）")
    metrics.add_argument("--out", required=True)
    metrics.add_argument("--since", default=None, help="起始时间，如 2026-11-01 00:00:00")
    metrics.add_argument("--until", default=None, help="结束时间（不含）")
    metrics.add_argument("--limit", type=int, default=500_000)
    metrics.set_defaults(func=export_metrics)

    decisions = sub.add_parser("decisions", help="agent_decision_loop → 决策链 JSONL")
    decisions.add_argument("--out", required=True)
    decisions.add_argument("--limit", type=int, default=50_000)
    decisions.set_defaults(func=export_decisions)

    inspections = sub.add_parser("inspections", help="inspector_event + 证据 → 标注候选 JSONL")
    inspections.add_argument("--out", required=True)
    inspections.add_argument("--limit", type=int, default=50_000)
    inspections.set_defaults(func=export_inspections)

    trajectories = sub.add_parser("trajectories", help="执行器事件 JSONL → 轨迹 JSONL")
    trajectories.add_argument("--input", required=True)
    trajectories.add_argument("--out", required=True)
    trajectories.set_defaults(func=export_trajectories)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

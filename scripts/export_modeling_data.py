# -*- coding: utf-8 -*-
"""
数学建模训练数据导出脚本
========================
从 SmartOpsAgent 的 MySQL 库导出建模所需数据集，输出到 data/modeling-export/。

数据源与用途映射：
  - inspector_event          -> 方案一：事件量时序预测、异常检测
  - inspection_verification  -> 方案一：人工复核结果（标签参考）
  - model_invocation_usage   -> 方案三：响应性能指标 / 方案一：延迟序列
  - agent_decision_loop      -> 方案三：执行闭环可靠性评价主数据
  - operation_run_record     -> 方案三：执行可靠性（成功率/超时/重试）
  - knowledge_candidate      -> 方案五：知识候选分类（附带导出）

派生数据集（建模直接可用的聚合层）：
  - hourly_event_series.csv    按小时聚合事件量与失败率（方案一 ARIMA/Prophet 输入）
  - model_usage_hourly.csv     按小时聚合模型调用量、失败率、平均延迟（方案一延迟预测输入）
  - loop_stage_metrics.csv     执行闭环各 stage 统计（方案三指标体系输入）

用法：
  python scripts/export_modeling_data.py
连接参数优先读环境变量，缺省回退 backend/.env.local，再回退本地默认值。
"""

import os
import sys
import warnings
from pathlib import Path

import pandas as pd
import pymysql

# Windows 控制台中文输出保护
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "modeling-export"
ENV_FILE = ROOT / "backend" / ".env.local"


def load_env_local() -> dict:
    """读取 backend/.env.local 的 KEY=VALUE，供连接参数回退。"""
    values = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                values[key.strip()] = val.strip()
    return values


def resolve_conn() -> dict:
    env = load_env_local()
    return {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USERNAME", env.get("MYSQL_USERNAME", "root")),
        "password": os.getenv("MYSQL_PASSWORD", env.get("MYSQL_PASSWORD", "root")),
        "database": os.getenv("MYSQL_DB", "smartops"),
        "charset": "utf8mb4",
    }


def fetch_all(conn, sql: str) -> pd.DataFrame:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            return pd.read_sql(sql, conn)
    except Exception as exc:
        print(f"  [跳过] 查询失败：{exc}")
        return pd.DataFrame()


def export_raw(conn):
    """原始明细导出：每个数据集一个 CSV。"""
    raw_queries = {
        # 方案一主数据：纠察事件流（含巡检结果，巡检经 recordInspection 写入此表）
        "inspector_events": """
            SELECT id, task_id, target, status, severity, category,
                   requires_human, agent_claim, reason, recommendation,
                   created_at
            FROM inspector_event
            ORDER BY created_at
        """,
        # 方案一辅助标签：人工复核结论
        "inspection_verification": """
            SELECT event_id, resolved, status, verified_at
            FROM inspection_verification
            ORDER BY verified_at
        """,
        # 方案三性能维度 + 方案一延迟序列：模型调用明细
        "model_invocation_usage": """
            SELECT id, user_id, connection_id, model_name, started_at,
                   status, duration_ms, input_tokens, output_tokens, total_tokens
            FROM model_invocation_usage
            ORDER BY started_at
        """,
        # 方案三主数据：决策闭环（结构化字段，confidence/outcome/stage/learned_count）
        "agent_decision_loop": """
            SELECT id, user_id, incident_key, source_type, stage, severity,
                   requires_human, outcome, confidence, learned_count,
                   reviewed_at, created_at, updated_at
            FROM agent_decision_loop
            ORDER BY created_at
        """,
        # 方案三执行可靠性：运维命令执行记录（status/started_at/ended_at）
        "operation_run_record": """
            SELECT id, trace_id, user_id, tool_id, status,
                   started_at, ended_at, created_at
            FROM operation_run_record
            ORDER BY started_at
        """,
        # 方案五：知识候选（source_type 可区分 LOG_DIAGNOSIS / SCIVERSE 等）
        "knowledge_candidates": """
            SELECT id, user_id, source_type, trace_id, tool_id, title,
                   status, created_at, updated_at
            FROM knowledge_candidate
            ORDER BY created_at
        """,
    }
    for name, sql in raw_queries.items():
        df = fetch_all(conn, sql)
        if df.empty:
            print(f"  {name}: 无数据，已跳过")
            continue
        path = OUT_DIR / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"  {name}: {len(df)} 行 -> {path.name}")
    return raw_queries


def aggregate_hourly_events(ev: pd.DataFrame) -> pd.DataFrame:
    """按小时聚合纠察事件：总量、高危量、需人工量、OPEN 占比。"""
    ev = ev.copy()
    ev["created_at"] = pd.to_datetime(ev["created_at"], errors="coerce")
    ev = ev.dropna(subset=["created_at"])
    hourly = (
        ev.set_index("created_at")
        .resample("1h")
        .agg(
            total=("severity", "size"),
            critical=("severity", lambda s: int((s.str.upper() == "CRITICAL").sum())),
            high=("severity", lambda s: int((s.str.upper() == "HIGH").sum())),
            requires_human=("requires_human", "sum"),
            open_events=("status", lambda s: int((s.str.upper().isin(["OPEN", "PENDING", "REVIEW"])).sum())),
        )
        .reset_index()
    )
    # OPEN 占比作为"失败率"代理指标
    hourly["open_ratio"] = (hourly["open_events"] / hourly["total"].clip(lower=1)).round(4)
    return hourly


def aggregate_model_usage(mu: pd.DataFrame) -> pd.DataFrame:
    """按小时聚合模型调用：调用量、失败率、平均/P95延迟、token。"""
    mu = mu.copy()
    mu["started_at"] = pd.to_datetime(mu["started_at"], errors="coerce")
    mu = mu.dropna(subset=["started_at"])
    mu["failed"] = ~mu["status"].str.upper().isin(["SUCCESS", "OK", "COMPLETED"])
    hourly_mu = (
        mu.set_index("started_at")
        .resample("1h")
        .agg(
            invocations=("status", "size"),
            failures=("failed", "sum"),
            avg_duration_ms=("duration_ms", "mean"),
            p95_duration_ms=("duration_ms", lambda s: s.quantile(0.95)),
            total_tokens=("total_tokens", "sum"),
        )
        .reset_index()
    )
    hourly_mu["failure_rate"] = (hourly_mu["failures"] / hourly_mu["invocations"].clip(lower=1)).round(4)
    return hourly_mu


def aggregate_loop_metrics(loop: pd.DataFrame) -> pd.DataFrame:
    """决策闭环 stage 维度统计：闭环完成率、需人工率、置信度、学习数。"""
    loop = loop.copy()
    stage_metrics = (
        loop.groupby("stage")
        .agg(
            total=("stage", "size"),
            requires_human=("requires_human", "sum"),
            avg_confidence=("confidence", "mean"),
            avg_learned_count=("learned_count", "mean"),
        )
        .reset_index()
    )
    # 已出决策（outcome 非空）视为闭环完成
    loop["closed"] = loop["outcome"].notna() & (loop["outcome"].astype(str).str.strip() != "")
    closed = loop.groupby("stage")["closed"].mean().rename("closed_ratio").reset_index()
    return stage_metrics.merge(closed, on="stage", how="left")


def export_derived(conn):
    """聚合层导出：建模论文的直接输入。"""
    # 1) 按小时聚合纠察事件 —— 方案一预测目标序列
    ev = fetch_all(conn, "SELECT severity, status, requires_human, created_at FROM inspector_event")
    if not ev.empty:
        hourly = aggregate_hourly_events(ev)
        path = OUT_DIR / "hourly_event_series.csv"
        hourly.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"  hourly_event_series: {len(hourly)} 行 -> {path.name}")

    # 2) 按小时聚合模型调用 —— 方案三性能指标
    mu = fetch_all(conn, "SELECT model_name, status, duration_ms, total_tokens, started_at FROM model_invocation_usage")
    if not mu.empty:
        hourly_mu = aggregate_model_usage(mu)
        path = OUT_DIR / "model_usage_hourly.csv"
        hourly_mu.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"  model_usage_hourly: {len(hourly_mu)} 行 -> {path.name}")

    # 3) 决策闭环 stage × outcome 交叉统计 —— 方案三指标体系
    loop = fetch_all(conn, "SELECT stage, severity, outcome, requires_human, confidence, learned_count FROM agent_decision_loop")
    if not loop.empty:
        stage_metrics = aggregate_loop_metrics(loop)
        path = OUT_DIR / "loop_stage_metrics.csv"
        stage_metrics.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"  loop_stage_metrics: {len(stage_metrics)} 行 -> {path.name}")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    conn_info = resolve_conn()
    print(f"连接目标：{conn_info['host']}:{conn_info['port']}/{conn_info['database']} (用户 {conn_info['user']})")
    conn = pymysql.connect(**conn_info)
    try:
        print("\n[原始明细导出]")
        export_raw(conn)
        print("\n[聚合层导出]")
        export_derived(conn)
    finally:
        conn.close()
    print(f"\n完成。输出目录：{OUT_DIR}")


if __name__ == "__main__":
    main()

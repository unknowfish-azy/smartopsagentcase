"""从 MySQL 导出真实故障案例 → P1-3 案例库格式。

复用 scripts/export_modeling_data.py 的风格：
  - pymysql + env / backend/.env.local / 显式 --db-*
  - CSV / JSONL / SQL INSERT 三种输出（--out 选择，默认 data/lake/raw/retrieval_cases.*）
  - 可选 --apply 直接 append 进 faiss 索引（调 P2-3 的 case_retriever.learn()）
  - 默认只导出 outcome 非空且 symptom≥10 字符的有效案例

Usage:
  # 1. 看一眼有多少有效案例（dry-run）
  python scripts/export_retrieval_cases.py

  # 2. 导出成 CSV + JSONL + SQL（默认路径 data/lake/raw/retrieval_cases.*）
  python scripts/export_retrieval_cases.py --out-dir data/lake/raw

  # 3. 只导出已解决（outcome=RESOLVED）的
  python scripts/export_retrieval_cases.py --outcome RESOLVED

  # 4. 导出后直接 append 进 faiss（会自动 encode + 持久化）
  python scripts/export_retrieval_cases.py --apply

  # 5. 自定义 DB 参数
  python scripts/export_retrieval_cases.py --db-host 10.0.0.5 --db-user ops --db-pass xxx
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 连接解析（复用 scripts/export_modeling_data.py 的风格）
# ---------------------------------------------------------------------------

def _load_dotenv(env_path: Path) -> dict[str, str]:
    env_map: dict[str, str] = {}
    if not env_path.is_file():
        return env_map
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env_map.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return env_map


def resolve_conn(args) -> dict[str, str]:
    """解析 MySQL 连接参数。优先级：--db-* > env > .env.local。"""
    repo_root = Path(__file__).resolve().parents[1]
    dotenv_map = _load_dotenv(repo_root / "backend" / ".env.local")

    return {
        "host": args.db_host or os.environ.get("MYSQL_HOST") or dotenv_map.get("MYSQL_HOST") or "localhost",
        "port": args.db_port or int(os.environ.get("MYSQL_PORT") or dotenv_map.get("MYSQL_PORT") or 3306),
        "user": args.db_user or os.environ.get("MYSQL_USERNAME") or dotenv_map.get("MYSQL_USERNAME") or "root",
        "password": args.db_pass or os.environ.get("MYSQL_PASSWORD") or dotenv_map.get("MYSQL_PASSWORD") or "",
        "database": args.db_name or os.environ.get("MYSQL_DATABASE") or dotenv_map.get("MYSQL_DATABASE") or "smartops",
    }


# ---------------------------------------------------------------------------
# 主查询
# ---------------------------------------------------------------------------

SELECT_SQL = """
SELECT
    incident_key,
    source_type,
    stage,
    severity,
    outcome,
    confidence,
    learned_count,
    symptom,
    analysis,
    evidence_json,
    decision,
    decision_basis,
    recommendation,
    lesson,
    reviewed_at,
    created_at,
    updated_at
FROM agent_decision_loop
WHERE 1=1
  AND incident_key IS NOT NULL
  AND CHAR_LENGTH(symptom) >= 10
{outcome_filter}
{stage_filter}
ORDER BY created_at DESC
LIMIT {limit}
"""

STAGE_TO_CATEGORY: dict[str, str] = {
    "ANALYZE": "other",
    "DECIDE": "other",
    "LEARNED": "other",
}

# 从 decision_basis 里尝试提取故障类别（启发式）
# 匹配顺序很重要——network_error 在 auth_error 前面，因为 "401 network error" 里 401 更准
_CATEGORY_HINTS: list[tuple[list[str], str]] = [
    (["oom", "outofmemory", "out of memory", "heap", "killed", "memory leak"], "oom"),
    (["disk_full", "no space", "disk usage", "inode", "wal", "logrotate", "100% disk", "disk full"], "disk_full"),
    (["segfault", "crash", "core dump", "process died", "exit code", "abort"], "process_crash"),
    (["401", "403", "unauthorized", "forbidden", "jwt", "jwks", "token expired", "certificate"], "auth_error"),
    (["connection refused", "econnrefused", "dial tcp", "connection reset", "broken pipe"], "connection_refused"),
    (["timeout", "502", "504", "deadline exceeded", "latency", "upstream", "nginx", "p99", "hang", "slow"], "timeout"),
    (["packet loss", "network error", "dns", "nxdomain", "network timeout", "can't reach", "cannot reach"], "network_error"),
]


def _guess_category(symptom: str, analysis: str, decision_basis: str | None, evidence_json: str | None = None) -> str:
    text_parts = [symptom or "", analysis or "", decision_basis or ""]
    if evidence_json:
        try:
            ev = json.loads(evidence_json)
            if isinstance(ev, list):
                text_parts.extend(str(e) for e in ev if e)
        except Exception:
            pass
    text = " ".join(text_parts).lower()
    for keywords, cat in _CATEGORY_HINTS:
        if any(k in text for k in keywords):
            return cat
    return "other"


def _to_action(decision: str | None, decision_basis: str | None) -> str:
    """从 decision / decision_basis 里提取动作。

    优先用 decision 字段（Agent 最终做了什么）；没的话从 decision_basis 里找。
    如果还是没有，返回 decision_basis 全文字符串（语义更重要）。
    """
    if decision and decision.strip() and decision.strip().lower() not in ("ignore", "none", "null"):
        return decision.strip()
    if decision_basis and decision_basis.strip():
        return decision_basis.strip()
    return "unknown"


def transform_row(row: dict[str, Any]) -> dict[str, Any]:
    """agent_decision_loop 行 → P1-3 案例库 schema。"""
    symptom = row.get("symptom") or ""
    analysis = row.get("analysis") or ""
    outcome_raw = (row.get("outcome") or "PENDING").upper()
    # outcome 标准化
    outcome_map = {
        "RESOLVED": "resolved",
        "MITIGATED": "mitigated",
        "FAILED": "failed",
        "PENDING": "pending",
        "": "pending",
    }
    outcome = outcome_map.get(outcome_raw, outcome_raw.lower())

    # severity 标准化
    sev_raw = (row.get("severity") or "MEDIUM").upper()
    sev_map = {"P0": "P0", "P1": "P1", "P2": "P2", "P3": "P3", "CRITICAL": "P0", "HIGH": "P1", "MEDIUM": "P2", "LOW": "P3"}
    severity = sev_map.get(sev_raw, "P2")

    category = _guess_category(symptom, analysis, row.get("decision_basis"), row.get("evidence_json"))
    action = _to_action(row.get("decision"), row.get("decision_basis"))

    evidence = row.get("evidence_json")
    evidence_list: list[str] = []
    if evidence:
        try:
            evidence_list = json.loads(evidence)
            if isinstance(evidence_list, list):
                evidence_list = [str(e) for e in evidence_list if e]
        except Exception:
            evidence_list = []

    return {
        "incident_key": row.get("incident_key") or f"DB-{int(datetime.now().timestamp())}",
        "category": category,
        "severity": severity,
        "stage": (row.get("stage") or "ANALYZE").upper(),
        "source_type": (row.get("source_type") or "MANUAL").upper(),
        "symptom": symptom,
        "analysis": analysis,
        "action_taken": action,
        "outcome": outcome,
        "lesson": row.get("lesson") or "",
        "recommendation": row.get("recommendation") or "",
        "evidence": evidence_list,
        "confidence": float(row.get("confidence") or 0.5),
        "learned_count": int(row.get("learned_count") or 0),
        "created_at": int(row.get("created_at").timestamp()) if row.get("created_at") else None,
        "reviewed_at": int(row.get("reviewed_at").timestamp()) if row.get("reviewed_at") else None,
    }


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------

def write_outputs(records: list[dict[str, Any]], out_dir: Path, formats: list[str]) -> dict[str, int]:
    """写 CSV / JSONL / SQL 三种格式，返回写入条数。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, int] = {}

    if "csv" in formats and records:
        import csv
        csv_path = out_dir / "retrieval_cases.csv"
        fieldnames = list(records[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in records:
                row = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v) for k, v in r.items()}
                writer.writerow(row)
        written["csv"] = len(records)
        print(f"  ✓ CSV      → {csv_path}  ({len(records)} rows)")

    if "jsonl" in formats and records:
        jsonl_path = out_dir / "retrieval_cases.jsonl"
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        written["jsonl"] = len(records)
        print(f"  ✓ JSONL    → {jsonl_path}  ({len(records)} rows)")

    if "sql" in formats and records:
        sql_path = out_dir / "retrieval_cases.sql"
        with open(sql_path, "w", encoding="utf-8") as f:
            f.write("-- P1-3 案例库导出 SQL INSERT\n")
            f.write(f"-- exported at {datetime.now(timezone.utc).isoformat()}\n")
            f.write("-- source: smartops.agent_decision_loop\n\n")
            for r in records:
                vals = [
                    _sql_quote(r["incident_key"]),
                    _sql_quote(r["category"]),
                    _sql_quote(r["severity"]),
                    _sql_quote(r["outcome"]),
                    _sql_quote(r["symptom"]),
                    _sql_quote(r["analysis"]),
                    _sql_quote(r["action_taken"]),
                    _sql_quote(r["lesson"]),
                    _sql_quote(r["recommendation"]),
                    str(r["confidence"]),
                ]
                f.write("INSERT INTO p13_case_index (incident_key, category, severity, outcome, symptom, analysis, action_taken, lesson, recommendation, confidence)\n")
                f.write(f"VALUES ({', '.join(vals)});\n\n")
        written["sql"] = len(records)
        print(f"  ✓ SQL      → {sql_path}  ({len(records)} rows)")

    return written


def _sql_quote(val: str | None) -> str:
    if val is None or val == "":
        return "NULL"
    escaped = str(val).replace("\\", "\\\\").replace("'", "''")
    return f"'{escaped}'"


def apply_to_faiss(records: list[dict[str, Any]]) -> int:
    """append 进 P1-3 faiss 案例库（调 case_retriever.learn()）。"""
    repo_root = Path(__file__).resolve().parents[1]
    ai_service_path = repo_root / "ai-service"
    if str(ai_service_path) not in sys.path:
        sys.path.insert(0, str(ai_service_path))
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    import os as _os
    _os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    _os.environ.setdefault("OMP_NUM_THREADS", "1")

    from app.services import case_retriever

    # 先拿到基线 index size
    state = case_retriever.get_state()
    before = len(state.index) if state.index else 0
    print(f"  faiss index before: {before}")

    new_count = 0
    skipped = 0
    for r in records:
        # 防重复——P2-3 learn 已内置，但我们提前检查可以少一次 encode
        if case_retriever.has_incident_key(r["incident_key"]):
            skipped += 1
            continue
        meta = {
            "incident_key": r["incident_key"],
            "category": r["category"],
            "severity": r["severity"],
            "symptom": r["symptom"],
            "analysis": r["analysis"],
            "action_taken": r["action_taken"],
            "outcome": r["outcome"],
            "lesson": r["lesson"],
            "recommendation": r["recommendation"],
            "evidence": r["evidence"],
            "confidence": r["confidence"],
            "learned_count": r["learned_count"],
            "created_at": r["created_at"],
        }
        result = case_retriever.learn(meta)
        if result.get("ok") and not result.get("skipped"):
            new_count += 1

    state = case_retriever.get_state()
    after = len(state.index) if state.index else 0
    print(f"  ✓ applied: +{new_count} new, {skipped} skipped, index now {after}")
    return new_count


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="导出 MySQL agent_decision_loop → P1-3 案例库格式")

    p.add_argument("--db-host", default=None)
    p.add_argument("--db-port", type=int, default=None)
    p.add_argument("--db-user", default=None)
    p.add_argument("--db-pass", default=None)
    p.add_argument("--db-name", default=None)

    p.add_argument("--out-dir", default=None, help="输出目录（默认 data/lake/raw）")
    p.add_argument("--formats", default="csv,jsonl,sql", help="输出格式，逗号分隔")
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--outcome", default=None, help="过滤 outcome（RESOLVED/FAILED/PENDING/MITIGATED）")
    p.add_argument("--stage", default=None, help="过滤 stage (DECIDE/LEARNED)")

    p.add_argument("--apply", action="store_true", help="导出后直接 append 进 faiss 索引")
    p.add_argument("--dry-run", action="store_true", help="只打印条数和分布，不写文件")

    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    conn_params = resolve_conn(args)

    print("=" * 60)
    print("P1-3 案例库导出脚本")
    print("=" * 60)
    print(f"  host={conn_params['host']}:{conn_params['port']}")
    print(f"  db={conn_params['database']}  user={conn_params['user']}")
    filters: list[str] = []
    if args.outcome:
        filters.append(f"outcome={args.outcome}")
    if args.stage:
        filters.append(f"stage={args.stage}")
    print(f"  filters: {', '.join(filters) if filters else '(none)'}")
    print(f"  limit: {args.limit}")
    print()

    import pymysql
    try:
        conn = pymysql.connect(
            host=conn_params["host"],
            port=int(conn_params["port"]),
            user=conn_params["user"],
            password=conn_params["password"],
            database=conn_params["database"],
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )
    except Exception as exc:
        print(f"✗ 连接失败: {exc}")
        print("  检查 backend/.env.local 里的 MYSQL_USERNAME / MYSQL_PASSWORD")
        return 1

    # 构造 SQL
    outcome_filter = f"  AND outcome = '{args.outcome}'" if args.outcome else ""
    stage_filter = f"  AND stage = '{args.stage}'" if args.stage else ""
    sql = SELECT_SQL.format(
        outcome_filter=outcome_filter,
        stage_filter=stage_filter,
        limit=args.limit,
    )

    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    conn.close()

    print(f"从 agent_decision_loop 读出 {len(rows)} 行")

    if not rows:
        print("⚠ 没数据，退出")
        return 0

    # 数据分布
    cat_dist: dict[str, int] = {}
    outcome_dist: dict[str, int] = {}
    lesson_count = 0
    action_count = 0
    for row in rows:
        rec = transform_row(row)
        cat_dist[rec["category"]] = cat_dist.get(rec["category"], 0) + 1
        outcome_dist[rec["outcome"]] = outcome_dist.get(rec["outcome"], 0) + 1
        if rec["lesson"]:
            lesson_count += 1
        if rec["action_taken"] and rec["action_taken"] != "unknown":
            action_count += 1

    print(f"\n分布：")
    print(f"  category:  {cat_dist}")
    print(f"  outcome:   {outcome_dist}")
    print(f"  has lesson: {lesson_count}/{len(rows)}")
    print(f"  has action: {action_count}/{len(rows)}")

    records = [transform_row(r) for r in rows]

    # Dry-run 模式：只打印，不写
    if args.dry_run:
        print("\n[dry-run] 不写文件也不 apply")
        for r in records[:3]:
            print(f"  → {r['incident_key']} [{r['category']}] {r['outcome']} lesson={bool(r['lesson'])}")
        return 0

    # 写文件
    formats = [f.strip() for f in args.formats.split(",") if f.strip()]
    out_dir = Path(args.out_dir) if args.out_dir else Path(__file__).resolve().parents[1] / "data" / "lake" / "raw"
    print(f"\n写输出 → {out_dir} (formats={formats})")
    written = write_outputs(records, out_dir, formats)

    # --apply
    if args.apply:
        print("\n应用到 faiss 索引...")
        apply_to_faiss(records)

    print("\n✓ 完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())

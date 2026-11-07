#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SEC 安全侧 E2E 夹具自举/清理（platform_http_e2e_20261106.py 的前置数据）。

背景：platform_http_e2e_20261106.py 依赖 4 个账号 + 3 条归属 inspector_event，
原先是人工 SQL 建的，脚本因此不可独立重放。本脚本把这段固化下来：

用法：
  python scripts/e2e/seed_sec_fixtures.py            # 建/确保夹具存在，打印 ID
  python scripts/e2e/seed_sec_fixtures.py --cleanup  # 清理夹具（账号/事件/审计/闭环）

夹具：
  e2e_admin  / E2eAdmin#2026  role=admin   + platform_admin_profile(level=root)
  e2e_admin2 / E2eAdmin#2026  role=admin   无治理档案（SEC-07 最小只读用例）
  e2e_op1    / E2eOp#2026     role=operator
  e2e_op2    / E2eOp#2026     role=operator
  inspector_event: e2e-op1-0001(op1) / e2e-op2-0001(op2) / e2e-internal-0001(NULL 归属)
"""

from __future__ import annotations

import sys

import bcrypt
import pymysql

MYSQL = dict(host="127.0.0.1", user="root", password="password",
             database="smartops", charset="utf8mb4", autocommit=True)

ACCOUNTS = [
    # username, password, role, governance_level
    ("e2e_admin", "E2eAdmin#2026", "admin", "root"),
    ("e2e_admin2", "E2eAdmin#2026", "admin", None),
    ("e2e_op1", "E2eOp#2026", "operator", None),
    ("e2e_op2", "E2eOp#2026", "operator", None),
]

EVENTS = [
    # id(=task_id，E2E 断言按 id 前缀匹配), target, severity, user (None=内部通道)
    ("e2e-op1-0001", "host-e2e-op1", "HIGH", "e2e_op1"),
    ("e2e-op2-0001", "host-e2e-op2", "HIGH", "e2e_op2"),
    ("e2e-internal-0001", "host-e2e-internal", "MEDIUM", None),
]


def connect():
    return pymysql.connect(**MYSQL)


def ensure_account(cur, username: str, password: str, role: str, level: str | None) -> int:
    cur.execute("SELECT id FROM app_user WHERE username=%s", (username,))
    row = cur.fetchone()
    digest = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    if row:
        user_id = row[0]
        # 密码重置为夹具约定值，保证脚本可重放
        cur.execute("UPDATE app_user SET password_hash=%s, role=%s, enabled=1 WHERE id=%s",
                    (digest, role, user_id))
    else:
        cur.execute(
            "INSERT INTO app_user(username, password_hash, role, enabled, created_at) "
            "VALUES(%s,%s,%s,1,NOW())", (username, digest, role))
        user_id = cur.lastrowid
    if level:
        cur.execute("SELECT 1 FROM platform_admin_profile WHERE user_id=%s AND revoked_at IS NULL",
                    (user_id,))
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO platform_admin_profile(user_id, level, appointed_by, appointed_at) "
                "VALUES(%s,%s,%s,NOW())", (user_id, level, user_id))
    else:
        # e2e_admin2 必须「无」治理档案，否则 SEC-07 用例失效
        cur.execute("DELETE FROM platform_admin_profile WHERE user_id=%s", (user_id,))
    return user_id


def seed() -> dict[str, int]:
    ids: dict[str, int] = {}
    conn = connect()
    try:
        with conn.cursor() as cur:
            for username, password, role, level in ACCOUNTS:
                ids[username] = ensure_account(cur, username, password, role, level)
            # 清掉上一轮残留闭环与事件，保证断言可重复（仅限夹具账号）
            cur.execute("DELETE FROM agent_decision_loop WHERE user_id IN (%s, %s)",
                        (ids["e2e_op1"], ids["e2e_op2"]))
            for event_id, target, severity, owner in EVENTS:
                user_id = ids[owner] if owner else None
                cur.execute("DELETE FROM inspector_event WHERE id=%s OR task_id=%s",
                            (event_id, event_id))
                cur.execute(
                    "INSERT INTO inspector_event(id, task_id, target, status, severity, category, "
                    "agent_claim, reason, recommendation, requires_human, metadata_json, created_at, user_id) "
                    "VALUES(%s,%s,%s,'OPEN',%s,'e2e','e2e fixture','E2E 归属验收夹具',"
                    "'ignore',0,'{}',NOW(),%s)",
                    (event_id, event_id, target, severity, user_id))
    finally:
        conn.close()
    return ids


def cleanup() -> None:
    conn = connect()
    try:
        with conn.cursor() as cur:
            usernames = tuple(a[0] for a in ACCOUNTS)
            placeholders = ",".join(["%s"] * len(usernames))
            cur.execute(
                f"DELETE FROM inspector_event WHERE user_id IN "
                f"(SELECT id FROM app_user WHERE username IN ({placeholders})) "
                f"OR task_id LIKE 'e2e-%%'", usernames)
            cur.execute(f"DELETE FROM agent_decision_loop WHERE user_id IN "
                        f"(SELECT id FROM app_user WHERE username IN ({placeholders}))", usernames)
            cur.execute(f"DELETE FROM platform_admin_profile WHERE user_id IN "
                        f"(SELECT id FROM app_user WHERE username IN ({placeholders}))", usernames)
            cur.execute(f"DELETE FROM security_audit_event WHERE actor_username IN ({placeholders})",
                        usernames)
            cur.execute(f"DELETE FROM app_user WHERE username IN ({placeholders})", usernames)
            print("[CLEANUP] 夹具账号/事件/闭环/档案/审计已清理")
    finally:
        conn.close()


def main() -> int:
    if "--cleanup" in sys.argv:
        cleanup()
        return 0
    ids = seed()
    print("[SEED] 夹具就绪：")
    for name, user_id in ids.items():
        print(f"  {name} -> id={user_id}")
    print("  inspector_event: e2e-op1-0001 / e2e-op2-0001 / e2e-internal-0001")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

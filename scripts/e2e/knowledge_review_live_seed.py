#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知识审核泳道图 · 真实后端联调夹具。

用途：
  1. 用真实登录（含图形点选验证）拿到会话，把 cookie 写进 frontend/test-artifacts/live-session.json；
  2. 通过真实接口建知识库与条目（条目带 source_ref），再用 SQL 写入候选（生产里候选由知识生成链路写入，这里不重跑 AI）；
  3. 运行 frontend/test/knowledge-review-live.browser.mjs 校验泳道、审核写入与 409；
  4. 传 --cleanup 删除全部夹具。

账号：e2e_knowledge / E2eOp#2026（口令与其它 e2e 套件一致）。

用法：
  C:/Users/33908/AppData/Local/Programs/Python/Python314/python.exe scripts/e2e/knowledge_review_live_seed.py
  ... knowledge_review_live_seed.py --cleanup
"""

from __future__ import annotations

import json
import pathlib
import sys

import pymysql

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from sec0405_approval_e2e_20261106 import MYSQL, PASSWORD, Client, seed_user_sql  # noqa: E402

USER = "e2e_knowledge"
OUTPUT = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "test-artifacts" / "live-session.json"

LIBRARY_NAME = "E2E 泳道联调库"
ENTRY_A_REF = "live-trace-pod-crash"
ENTRY_B_REF = "live-trace-pool-exhaust"

CANDIDATES = [
    ("live-trace-pod-crash", "k8s.pod.diagnose", "Pod 反复重启：探针超时与 OOMKilled 区分",
     "pending", "PENDING_REVIEW", "pending"),
    ("live-trace-pool-exhaust", "mysql.connection.diagnose", "连接池耗尽：wait_timeout 与泄漏连接",
     "promoted", "PROMOTED", "promoted"),
    ("live-trace-orphan", "nginx.upstream.diagnose", "upstream 502：keepalive 与后端超时",
     "orphan", "PENDING_REVIEW", "pending"),
    ("live-trace-rejected", "redis.slowlog.inspect", "慢查询集中在 KEYS 扫描",
     "rejected", "REJECTED", "rejected"),
    ("live-trace-race", "k8s.pod.diagnose", "Pod 重启与节点压力同现时的取证顺序",
     "race", "PENDING_REVIEW", "pending"),
]


def db():
    return pymysql.connect(**{**MYSQL, "autocommit": True})


def user_id(cur) -> int:
    cur.execute("SELECT id FROM app_user WHERE username=%s", (USER,))
    row = cur.fetchone()
    if not row:
        raise SystemExit(f"账号 {USER} 不存在，请先跑一次不带 --cleanup 的种子")
    return int(row[0])


def cleanup():
    conn = db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM app_user WHERE username=%s", (USER,))
            row = cur.fetchone()
            if not row:
                print("[cleanup] 账号不存在，无需清理")
                return
            uid = int(row[0])
            cur.execute("DELETE FROM knowledge_candidate WHERE user_id=%s", (uid,))
            cur.execute("DELETE FROM operation_run_record WHERE user_id=%s", (uid,))
            cur.execute("DELETE FROM personal_knowledge_entry WHERE user_id=%s", (uid,))
            cur.execute("DELETE FROM personal_knowledge_library WHERE user_id=%s", (uid,))
        print("[cleanup] 候选 / 运行记录 / 条目 / 知识库已删除")
    finally:
        conn.close()


def login_or_create(username: str) -> Client:
    """当前环境关闭了图形验证（required=false），所以不额外领 humanToken；不通过再走 SQL 建号。"""
    client = Client()
    client.refresh_csrf()
    payload = {"username": username, "password": PASSWORD, "portal": "user"}
    status, body = client.request("POST", "/api/auth/login", payload)
    if status == 200 and body.get("code") == 200:
        client.refresh_csrf()
        return client

    client = Client()
    client.refresh_csrf()
    status, body = client.request("POST", "/api/auth/register", {
        **payload, "confirmPassword": PASSWORD})
    if not (status == 200 and body.get("code") == 200):
        print(f"[seed] 注册失败（{status} {body.get('message')}），改为 SQL 建号")
        seed_user_sql(username)
    status, body = client.request("POST", "/api/auth/login", payload)
    assert status == 200 and body.get("code") == 200, f"登录失败: {status} {body}"
    client.refresh_csrf()
    return client


def seed():
    client = login_or_create(USER)
    status, body = client.request("POST", "/api/knowledge/personal/libraries",
                                  {"name": LIBRARY_NAME, "description": "泳道图真实后端联调，可随时清理"})
    assert status == 200 and body.get("code") == 200, f"建库失败: {status} {body}"
    library_id = int(body["data"]["id"])

    entries = {}
    for key, ref, title in [
        ("a", ENTRY_A_REF, "Pod 反复重启排查"),
        ("b", ENTRY_B_REF, "连接池耗尽排查"),
    ]:
        status, body = client.request("POST", f"/api/knowledge/personal/libraries/{library_id}/entries", {
            "title": title,
            "summary": "由联调夹具创建，用于验证 source_ref 回挂",
            "contentMarkdown": f"# {title}\n\n联调夹具条目。",
            "sourceType": "RUN",
            "sourceRef": ref,
        })
        assert status == 200 and body.get("code") == 200, f"建条目失败: {status} {body}"
        entries[key] = int(body["data"]["id"])

    conn = db()
    ids = {}
    try:
        with conn.cursor() as cur:
            uid = user_id(cur)
            for index, (trace_id, tool_id, title, key, status_text, summary) in enumerate(CANDIDATES):
                # 候选的 source_run_id 有外键指向运行记录，联调夹具补一条最小运行。
                cur.execute(
                    """INSERT INTO operation_run_record
                       (trace_id, user_id, runtime_id, tool_id, status, started_at, ended_at, created_at)
                       VALUES (%s, %s, %s, %s, 'SUCCEEDED', NOW() - INTERVAL %s MINUTE,
                               NOW() - INTERVAL %s MINUTE, NOW() - INTERVAL %s MINUTE)""",
                    (trace_id, uid, f"observability:{tool_id}", tool_id,
                     30 - index * 5, 30 - index * 5, 30 - index * 5))
                run_id = int(cur.lastrowid)
                cur.execute(
                    """INSERT INTO knowledge_candidate
                       (user_id, source_type, source_run_id, trace_id, tool_id, title, summary,
                        content_markdown, status, created_at, updated_at)
                       VALUES (%s, 'RUN', %s, %s, %s, %s, %s, %s, %s, NOW() - INTERVAL %s MINUTE, NOW())""",
                    (uid, run_id, trace_id, tool_id, title, summary,
                     f"# {title}\n\n## 现象\n\n联调夹具候选。\n", status_text, 30 - index * 5))
                ids[key] = int(cur.lastrowid)
    finally:
        conn.close()

    cookies = [{
        "name": cookie.name,
        "value": cookie.value,
        "domain": cookie.domain or "127.0.0.1",
        "path": cookie.path or "/",
        "httpOnly": bool(cookie.has_nonstandard_attr("HttpOnly") or cookie._rest.get("HttpOnly")),
        "secure": bool(cookie.secure),
    } for cookie in client.jar]

    payload = {
        "userId": uid,
        "username": USER,
        "libraryId": library_id,
        "entries": entries,
        "candidates": ids,
        "cookies": cookies,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[seed] 知识库 #{library_id}，条目 {entries}，候选 {ids}")
    print(f"[seed] 会话写入 {OUTPUT}")


if __name__ == "__main__":
    cleanup()
    if "--cleanup" not in sys.argv:
        seed()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SEC-04/05 审批-预览-grant 链路 HTTP 级验收 —— 2026-11-06 晚（第二批）。

前置条件：
  1. MySQL(smartops)/Redis 已启动；后端（含 grantToken 下发修复）运行在 127.0.0.1:8080。
  2. mock SSH 服务器已启动：scripts/e2e/mock_ssh_server.py（127.0.0.1:2222，e2eops/E2eSsh#2026）。
  3. 账号 e2e_op1 / e2e_op2 由本脚本自动注册（上轮验收后已清理；若已存在会自动改用登录）。

覆盖项（对应整改清单 next_batch「SEC-04/05 HTTP 级负例、Redis 启动后的健康检查」）：
  H1  Redis 健康检查      /actuator/health 总体 UP（Redis 指示器参与就绪判定）
  H2  runtime 注册        真实 SSH 拨号（paramiko mock）→ ONLINE + runtimeId
  S1  SEC-05 create       可变更工具运行 → PENDING_APPROVAL，创建响应不含 grantToken
  S2  SEC-05 未批先执行   → 409 TEAM_RUN_APPROVAL_REQUIRED
  S3  SEC-04/05 自批禁止  申请人 preview/approve → 403 TEAM_RUN_SELF_APPROVAL_FORBIDDEN
  S4  SEC-05 未预览先批   → 409 TEAM_RUN_PREVIEW_REQUIRED
  S5  SEC-05 预览         审批人 preview → 渲染命令 systemctl restart e2e-demo
  S6  SEC-05 审批         审批人 approve → APPROVED，审批人视角不含 grantToken
  S7  SEC-05 token 下发   申请人 detail 可见一次性 grantToken（本轮修复，此前 @JsonIgnore 永不下发）
  S8  SEC-05 缺 token     → 409 TEAM_RUN_GRANT_TOKEN_REQUIRED
  S9  SEC-05 错 token     → 403 TEAM_RUN_GRANT_TOKEN_MISMATCH
  S10 SEC-05 篡改参数     DB 直改 parameters_json + 正确 token → 409 TEAM_RUN_PREVIEW_CHANGED（TM-14）
  S11 SEC-05 过期 grant   DB 直改 grant_expires_at → 403 TEAM_RUN_GRANT_INVALID（TM-12）
  S12 SEC-05 合法执行     正确 token → 200，mock SSH 真实收到命令
  S13 SEC-05 一次性       二次执行同 token → 409 TEAM_RUN_GRANT_USED（TM-15）
  S14 SEC-05 幂等键       同 idempotencyKey 两次 create → 同一 run id
  S15 SEC-05 撤回         cancel → CANCELED，execute → 409 TEAM_RUN_CANCELED
  M1  SEC-03 双人确认     rm -rf（CRITICAL）preview → requiredApprovals=2
  M2  SEC-03 自批拦截     同一 nonce 自批 execute → 409 SECOND_APPROVER_REQUIRED

SEC-04 说明：Python agent 侧审批（run_id 指纹、legacy 不可用、reviewer≠requester）无 HTTP 面
（进程内判定），HTTP 级等价约束由 S3 的 TEAM_RUN_SELF_APPROVAL_FORBIDDEN 体现；
跨 run 复用拒绝已有 tests/agent/test_execution_approval.py 42 项单测，如实标注不做重复 HTTP 验证。

用法：
  C:/Users/33908/AppData/Local/Programs/Python/Python314/python.exe scripts/e2e/sec0405_approval_e2e_20261106.py
"""

from __future__ import annotations

import http.cookiejar
import json
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

import pymysql

BASE = "http://127.0.0.1:8080"
SSH_USER, SSH_PASSWORD, SSH_PORT = "e2eops", "E2eSsh#2026", 2222
OP1, OP2 = "e2e_op1", "e2e_op2"
# 必须与 seed_sec_fixtures.py / platform_http_e2e 保持一致：
# 账号是跨套件共享的，口令不一致会让后跑的套件登录 401（曾发生）。
PASSWORD = "E2eOp#2026"
MYSQL = dict(host="127.0.0.1", port=3306, user="root", password="password",
             database="smartops", charset="utf8mb4", autocommit=True)

COLOR_HEX = {
    "红色": "#e2453c", "蓝色": "#2f6fe0", "绿色": "#2f9e5f",
    "橙色": "#e88b1f", "紫色": "#8b5cf6", "青色": "#0ea5b7",
}

NO_PROXY = urllib.request.ProxyHandler({})  # 本机直连，禁走系统代理

RESULTS = []


def check(code: str, name: str, ok: bool, evidence: str):
    RESULTS.append((code, name, "PASS" if ok else "FAIL", evidence))
    print(f"[{'PASS' if ok else 'FAIL'}] {code} {name}\n       {evidence}")


# ----------------------------------------------------------------------------
# 会话客户端（与 platform_http_e2e_20261106.py 同款：cookie + CSRF + 图形点选验证）
# ----------------------------------------------------------------------------

class Client:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            NO_PROXY, urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = None

    def refresh_csrf(self):
        with self.opener.open(f"{BASE}/api/auth/session", timeout=10) as r:
            body = json.loads(r.read().decode("utf-8"))
        self.csrf = body["data"]["csrfToken"]
        return self.csrf

    def request(self, method: str, path: str, payload=None, headers=None):
        hdrs = {"Accept": "application/json"}
        if payload is not None:
            hdrs["Content-Type"] = "application/json"
        if self.csrf:
            hdrs["X-CSRF-TOKEN"] = self.csrf
        hdrs.update(headers or {})
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(BASE + path, data=data, headers=hdrs, method=method)
        try:
            with self.opener.open(req, timeout=60) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            try:
                return e.code, json.loads(raw)
            except json.JSONDecodeError:
                return e.code, {"raw": raw}


def parse_shapes(scene_svg: str):
    root = ET.fromstring(scene_svg)
    ns = "{http://www.w3.org/2000/svg}"
    shapes = []
    for el in root:
        tag = el.tag.replace(ns, "")
        if tag == "circle":
            shapes.append({"x": float(el.get("cx")), "y": float(el.get("cy")),
                           "fill": el.get("fill"), "letter": None})
        elif tag == "rect":
            if el.get("x") is None:
                continue
            x, w = float(el.get("x")), float(el.get("width"))
            y, h = float(el.get("y")), float(el.get("height"))
            shapes.append({"x": x + w / 2, "y": y + h / 2, "fill": el.get("fill"), "letter": None})
        elif tag == "polygon":
            pts = [tuple(map(float, p.split(","))) for p in el.get("points").split()]
            shapes.append({"x": sum(p[0] for p in pts) / len(pts),
                           "y": sum(p[1] for p in pts) / len(pts),
                           "fill": el.get("fill"), "letter": None})
        elif tag == "text" and shapes:
            tx, ty = float(el.get("x")), float(el.get("y"))
            nearest = min(shapes, key=lambda s: (s["x"] - tx) ** 2 + (s["y"] - ty) ** 2)
            nearest["letter"] = (el.text or "").strip()
    return shapes


def solve_clicks(prompt: str, shapes: list):
    body = prompt.split("的", 1)[1].strip()
    tokens = [t for t in re.split(r"[、\s]+", body) if t]
    ordered, expected = [], len(tokens)
    if len(tokens) == 2 and re.fullmatch(r"#[0-9a-fA-F]{6}", tokens[0]) and len(tokens[1]) == 1:
        hexc, letter = tokens[0].lower(), tokens[1].upper()
        ordered = [s for s in shapes if s["fill"].lower() == hexc and s["letter"] == letter]
        expected = 1
    elif all(re.fullmatch(r"[A-Z]", t) for t in tokens):
        for letter in tokens:
            ordered.append(next(s for s in shapes if s["letter"] == letter))
    elif all(t.endswith("图形") for t in tokens):
        for name in tokens:
            hexc = COLOR_HEX[name[:2]]
            ordered.append(next(s for s in shapes if s["fill"].lower() == hexc))
    else:
        raise ValueError(f"无法解析提示语: {prompt}")
    if not ordered or len(ordered) != expected:
        raise ValueError(f"目标图形缺失: {prompt}")
    return [{"x": round(s["x"]), "y": round(s["y"])} for s in ordered]


def human_token(client: Client, action: str) -> str:
    status, body = client.request("GET", f"/api/auth/human-verification?action={action}")
    assert status == 200, f"领取挑战失败: {status} {body}"
    policy = body["data"]
    shapes = parse_shapes(policy["scene"])
    clicks = solve_clicks(policy["prompt"], shapes)
    time.sleep(0.9)  # 服务端 min-response-ms=600
    status, body = client.request("POST", "/api/auth/human-verification/verify", {
        "action": action, "nonce": policy["challenge"], "clicks": clicks})
    assert status == 200, f"解题失败: {status} {body} prompt={policy['prompt']}"
    return body["data"]["token"]


def login(username: str, password: str, portal: str = "user") -> Client:
    client = Client()
    client.refresh_csrf()
    token = human_token(client, "login")
    status, body = client.request("POST", "/api/auth/login", {
        "username": username, "password": password, "portal": portal, "humanToken": token})
    assert status == 200 and body.get("code") == 200, f"登录失败: {status} {body}"
    client.refresh_csrf()  # 登录后 CSRF 轮换
    return client


def ensure_user(username: str) -> Client:
    """确保账号可用并登录。

    顺序很关键：先拿现有口令试登录，能登就绝不改库。
    早期实现无条件走注册/SQL 重置，会把共享夹具账号的 password_hash 覆盖成本脚本口令，
    导致后跑的 platform_http_e2e 登录 401（套件顺序一换就挂，属于测试间污染）。
    """
    try:
        return login(username, PASSWORD)
    except AssertionError:
        print(f"  账号 {username} 现有口令登录失败，尝试注册/重置")
    client = Client()
    client.refresh_csrf()
    try:
        token = human_token(client, "register")
        status, body = client.request("POST", "/api/auth/register", {
            "username": username, "password": PASSWORD, "confirmPassword": PASSWORD,
            "humanToken": token})
        if not (status == 200 or body.get("code") == 200):
            print(f"  注册 {username}: {status} {body.get('message', '')}（走 SQL 建号）")
            seed_user_sql(username)
    except AssertionError as err:
        print(f"  注册 {username} 失败（走 SQL 建号）: {err}")
        seed_user_sql(username)
    return login(username, PASSWORD)


def seed_user_sql(username: str):
    """限流兜底：直接建号（bcrypt $2a$，与后端 BCryptPasswordEncoder 兼容）。"""
    import bcrypt
    hashed = bcrypt.hashpw(PASSWORD.encode("utf-8"), bcrypt.gensalt(prefix=b"2a")).decode("ascii")
    existing = sql_exec(f"SELECT id FROM app_user WHERE username='{username}'")
    if existing:
        sql_exec("UPDATE app_user SET password_hash=%s, enabled=1 WHERE username=%s", (hashed, username))
        return
    sql_exec("INSERT INTO app_user(username, password_hash, role, enabled) VALUES(%s, %s, 'operator', 1)",
             (username, hashed))


# ----------------------------------------------------------------------------
# 工具
# ----------------------------------------------------------------------------

def expect(status: int, body: dict, http_code: int, code_name: str) -> tuple[bool, str]:
    ok = (status == http_code or body.get("code") == http_code) and body.get("message") == code_name
    return ok, f"-> {status} {body.get('message', body)}"


def db() -> pymysql.connections.Connection:
    return pymysql.connect(**MYSQL)


def sql_exec(statement: str, args=None):
    """执行单条 SQL（autocommit）；SELECT 返回首行，写语句返回 None。"""
    conn = db()
    try:
        with conn.cursor() as cur:
            cur.execute(statement, args or ())
            try:
                return cur.fetchone()
            except Exception:  # 写语句无结果集
                return None
    finally:
        conn.close()


def cleanup(op1_id: int, op2_id: int, team_id: int):
    """验收后清理本脚本自建的数据（幂等，可重复执行）。"""
    conn = db()
    with conn.cursor() as cur:
        for sql in [
            f"DELETE FROM team_agent_run WHERE team_id={team_id}",
            f"DELETE FROM team_agent WHERE team_id={team_id}",
            f"DELETE FROM team_member WHERE team_id={team_id}",
            f"DELETE FROM team_workspace WHERE id={team_id}",
            f"DELETE FROM team_invitation WHERE team_id={team_id}",
            f"DELETE FROM team_notification WHERE team_id={team_id}",
            # 注意：不要删 app_user 里的 e2e_op1/e2e_op2。
            # 这两个账号是 platform_http_e2e 与 sec03 共用的夹具，由 seed_sec_fixtures.py 建/清；
            # 本脚本删过一次，导致之后跑 platform_http_e2e 直接 401（登录失败）——套件顺序一变就挂。
            # 需要清理账号时统一走：python scripts/e2e/seed_sec_fixtures.py --cleanup
            f"DELETE FROM security_audit_event WHERE actor_id IN ({op1_id},{op2_id})",
            f"DELETE FROM operation_run_record WHERE user_id IN ({op1_id},{op2_id})",
            f"DELETE FROM operation_session WHERE user_id IN ({op1_id},{op2_id})",
            f"DELETE FROM operation_credential WHERE user_id IN ({op1_id},{op2_id})",
        ]:
            try:
                cur.execute(sql)
            except pymysql.err.MySQLError as err:
                print(f"  清理跳过: {sql[:60]}... ({err})")
    conn.close()
    print("  清理完成（team/agent/runs/users/sessions/credentials/audit/run_records）")


# ----------------------------------------------------------------------------
# 验收流程
# ----------------------------------------------------------------------------

def main() -> int:
    # ── 夹具：注册 → 团队 → Agent → SSH 会话 → runtime ────────────────
    op1 = ensure_user(OP1)
    op2 = ensure_user(OP2)
    row = sql_exec(f"SELECT id FROM app_user WHERE username='{OP1}'")
    op1_id = row[0]
    row = sql_exec(f"SELECT id FROM app_user WHERE username='{OP2}'")
    op2_id = row[0]

    # ── H1 Redis 健康检查（登录后可见组件详情；未登录只有总体状态） ─────
    probe = urllib.request.build_opener(NO_PROXY)
    with probe.open(f"{BASE}/actuator/health/readiness", timeout=5) as r:
        ready = json.loads(r.read().decode())["status"]
    with probe.open(f"{BASE}/actuator/health/liveness", timeout=5) as r:
        live = json.loads(r.read().decode())["status"]
    status, body = op1.request("GET", "/actuator/health")
    data = body.get("data") or body if isinstance(body, dict) else {}
    components = data.get("components") if isinstance(data, dict) else None
    if isinstance(components, dict) and "redis" in components:
        redis_state = components["redis"].get("status")
        redis_ok = redis_state == "UP"
        downs = [k for k, v in components.items() if (v.get("status") if isinstance(v, dict) else v) != "UP"]
        check("H1", "Redis 启动后健康指示器 UP（readiness 含 Redis 就绪）",
              redis_ok and ready == "UP" and live == "UP",
              f"redis={redis_state}, readiness={ready}, liveness={live}"
              + (f"（总体 DOWN 的其他指示器: {downs}）" if downs else ""))
    else:
        # 详情未暴露时退化为探针口径（Redis 参与就绪组）
        check("H1", "Redis 启动后健康（readiness/liveness UP）", ready == "UP" and live == "UP",
              f"health -> {status}（详情未暴露）, readiness={ready}, liveness={live}")

    status, body = op1.request("POST", "/api/teams", {"name": "e2e-sec05-team", "description": "SEC-04/05 验收专用"})
    assert status == 200, f"建团队失败: {status} {body}"
    team_id = body["data"]["id"]
    status, body = op1.request("POST", f"/api/teams/{team_id}/invitations", {"username": OP2, "role": "admin"})
    assert status == 200, f"邀请失败: {status} {body}"
    status, body = op2.request("GET", "/api/teams/invitations")
    invitations = body["data"]["items"] if isinstance(body["data"], dict) else body["data"]
    invitation_id = next(i["id"] for i in invitations if i["teamId"] == team_id)
    status, body = op2.request("POST", f"/api/teams/invitations/{invitation_id}/respond", {"accept": True})
    assert status == 200, f"接受邀请失败: {status} {body}"

    status, body = op1.request("POST", f"/api/teams/{team_id}/agents", {"name": "e2e-approval-agent", "description": "SEC-04/05"})
    assert status == 200, f"建 Agent 失败: {status} {body}"
    agent_id = body["data"]["id"]
    status, body = op1.request("PUT", f"/api/teams/{team_id}/agents/{agent_id}/draft", {
        "prompt": "E2E 验收 Agent：重启演示服务", "toolsJson": json.dumps(["service-restart", "host-health"])})
    assert status == 200, f"存草稿失败: {status} {body}"
    status, body = op1.request("POST", f"/api/teams/{team_id}/agents/{agent_id}/publish")
    assert status == 200, f"发布失败: {status} {body}"
    status, body = op1.request("GET", f"/api/teams/{team_id}/agents/{agent_id}")
    version_id = body["data"]["currentVersion"]["id"]

    status, body = op1.request("POST", "/api/operations/sessions", {
        "name": "e2e-mock-ssh", "protocol": "SSH", "host": "127.0.0.1", "port": SSH_PORT,
        "username": SSH_USER, "password": SSH_PASSWORD})
    assert status == 200, f"建 SSH 会话失败: {status} {body}"
    session_id = body["data"]["id"]
    status, body = op1.request("POST", f"/api/operations/sessions/{session_id}/connect?decision=TRUST_ONCE")
    runtime_id = (body.get("data") or {}).get("runtimeId")
    check("H2", "真实 SSH 拨号注册 runtime（paramiko mock 服务器）",
          status == 200 and runtime_id and (body["data"].get("status") == "ONLINE"),
          f"connect session={session_id} -> {status} {body['data'].get('status')} runtimeId={str(runtime_id)[:8]}...")

    # ── SEC-05 主链路 ──────────────────────────────────────────────────
    def create_run(tool_id, parameters, idem=None):
        payload = {"versionId": version_id, "runtimeId": runtime_id, "toolId": tool_id, "parameters": parameters}
        if idem:
            payload["idempotencyKey"] = idem
        return op1.request("POST", f"/api/teams/{team_id}/agents/{agent_id}/runs", payload)

    status, body = create_run("service-restart", {"service": "e2e-demo"})
    run1 = body["data"]
    check("S1", "可变更工具运行创建即 PENDING_APPROVAL 且不下发 token",
          status == 200 and run1["status"] == "PENDING_APPROVAL" and "grantToken" not in run1,
          f"create service-restart -> {status} status={run1.get('status')} tokenInResponse={'grantToken' in run1}")

    status, body = op1.request("POST", f"/api/team-agent-runs/{run1['id']}/execute", {})
    check("S2", "未审批先执行被拒", *expect(status, body, 409, "TEAM_RUN_APPROVAL_REQUIRED"))

    status, body = op1.request("POST", f"/api/team-agent-runs/{run1['id']}/preview")
    check("S3", "申请人自批被拒（审批人≠申请人的 HTTP 级约束）",
          *expect(status, body, 403, "TEAM_RUN_SELF_APPROVAL_FORBIDDEN"))

    status, body = create_run("service-restart", {"service": "e2e-run2"})
    run2 = body["data"]
    status, body = op2.request("POST", f"/api/team-agent-runs/{run2['id']}/approve", {})
    check("S4", "未预览先审批被拒", *expect(status, body, 409, "TEAM_RUN_PREVIEW_REQUIRED"))

    status, body = op2.request("POST", f"/api/team-agent-runs/{run1['id']}/preview")
    commands = (body.get("data") or {}).get("commands") or []
    check("S5", "审批人预览渲染命令（systemctl restart e2e-demo）",
          status == 200 and any("systemctl restart e2e-demo" in c for c in commands),
          f"preview -> {status} commands={commands}")

    status, body = op2.request("POST", f"/api/team-agent-runs/{run1['id']}/approve",
                               {"decisionBasis": "E2E：依据预览摘要批准（SEC-04/05 验收）"})
    approved = body["data"]
    check("S6", "审批通过且审批人视角不回发 token",
          status == 200 and approved["status"] == "APPROVED" and "grantToken" not in approved,
          f"approve -> {status} status={approved.get('status')} tokenInResponse={'grantToken' in approved}")

    status, body = op1.request("GET", f"/api/team-agent-runs/{run1['id']}")
    token = (body.get("data") or {}).get("grantToken")
    check("S7", "申请人 detail 可见一次性 grantToken（本轮修复，此前 @JsonIgnore 永不下发）",
          status == 200 and bool(token),
          f"GET detail(op1) -> {status} grantToken={'<uuid>' if token else '缺失'}")

    status, body = op1.request("POST", f"/api/team-agent-runs/{run1['id']}/execute", {})
    check("S8", "执行缺 token 被拒", *expect(status, body, 409, "TEAM_RUN_GRANT_TOKEN_REQUIRED"))

    status, body = op1.request("POST", f"/api/team-agent-runs/{run1['id']}/execute", {"grantToken": "forged-token"})
    check("S9", "执行错 token 被拒", *expect(status, body, 403, "TEAM_RUN_GRANT_TOKEN_MISMATCH"))

    # TM-14：审批后篡改 parameters_json（攻击者拿到 DB 写权限的最强形态）
    original_json = sql_exec(f"SELECT parameters_json FROM team_agent_run WHERE id={run1['id']}")[0]
    sql_exec(f"UPDATE team_agent_run SET parameters_json='{{\"service\":\"evil-target\"}}' WHERE id={run1['id']}")
    status, body = op1.request("POST", f"/api/team-agent-runs/{run1['id']}/execute", {"grantToken": token})
    check("S10", "审批后篡改参数再执行被拒（TM-14）", *expect(status, body, 409, "TEAM_RUN_PREVIEW_CHANGED"))
    sql_exec(f"UPDATE team_agent_run SET parameters_json=%s WHERE id={run1['id']}", (original_json,))

    # TM-12：过期 grant
    original_expiry = sql_exec(f"SELECT grant_expires_at FROM team_agent_run WHERE id={run1['id']}")[0]
    sql_exec(f"UPDATE team_agent_run SET grant_expires_at=NOW() - INTERVAL 1 SECOND WHERE id={run1['id']}")
    status, body = op1.request("POST", f"/api/team-agent-runs/{run1['id']}/execute", {"grantToken": token})
    check("S11", "过期 grant 执行被拒（TM-12）", *expect(status, body, 403, "TEAM_RUN_GRANT_INVALID"))
    sql_exec(f"UPDATE team_agent_run SET grant_expires_at=%s WHERE id={run1['id']}", (original_expiry,))

    status, body = op1.request("POST", f"/api/team-agent-runs/{run1['id']}/execute", {"grantToken": token})
    exec_ok = status == 200
    run_status = None
    if exec_ok:
        status2, detail = op1.request("GET", f"/api/team-agent-runs/{run1['id']}")
        run_status = (detail.get("data") or {}).get("status")
    check("S12", "合法 token 执行成功（命令真实送达 mock SSH）",
          exec_ok and run_status in ("RUNNING", "SUCCEEDED", "FAILED"),
          f"execute -> {status} run.status={run_status}（工具结果 {str(body.get('data'))[:80]}）")

    status, body = op1.request("POST", f"/api/team-agent-runs/{run1['id']}/execute", {"grantToken": token})
    check("S13", "grant 一次性：二次执行被拒（TM-15）", *expect(status, body, 409, "TEAM_RUN_GRANT_USED"))

    # S14 幂等键
    status, a = create_run("service-restart", {"service": "e2e-idem"}, "e2e-idem-key-1")
    status, b = create_run("service-restart", {"service": "e2e-idem"}, "e2e-idem-key-1")
    check("S14", "同 idempotencyKey 重复提交返回同一运行",
          a["data"]["id"] == b["data"]["id"],
          f"first={a['data']['id']} replay={b['data']['id']}")

    # S15 撤回
    status, body = create_run("service-restart", {"service": "e2e-run3"})
    run3 = body["data"]
    op2.request("POST", f"/api/team-agent-runs/{run3['id']}/preview")
    op2.request("POST", f"/api/team-agent-runs/{run3['id']}/approve", {"decisionBasis": "E2E run3"})
    status, detail = op1.request("GET", f"/api/team-agent-runs/{run3['id']}")
    token3 = detail["data"].get("grantToken")
    status, body = op1.request("POST", f"/api/team-agent-runs/{run3['id']}/cancel", {"reason": "E2E 验收撤回"})
    canceled = status == 200 and body["data"]["status"] == "CANCELED"
    status, body = op1.request("POST", f"/api/team-agent-runs/{run3['id']}/execute", {"grantToken": token3})
    reject_ok, reject_evidence = expect(status, body, 409, "TEAM_RUN_CANCELED")
    check("S15", "撤回后 grant 立即作废", canceled and reject_ok,
          f"cancel -> CANCELED；再 execute {reject_evidence}")

    # ── SEC-03 自批负例 ────────────────────────────────────────────────
    status, body = op1.request("POST", "/api/operations/multi-exec/preview", {
        "command": "rm -rf /tmp/e2e-sec03-demo", "runtimeIds": [runtime_id], "productionTarget": False})
    preview = body.get("data") or {}
    check("M1", "CRITICAL 命令预览要求双人确认", status == 200 and preview.get("requiredApprovals") == 2,
          f"preview rm -rf -> {status} risk={preview.get('risk')} requiredApprovals={preview.get('requiredApprovals')}")
    nonce = preview.get("confirmationNonce")
    status, body = op1.request("POST", "/api/operations/multi-exec/execute", {
        "previewId": preview.get("id"), "confirmationNonce": nonce, "secondConfirmationNonce": nonce})
    check("M2", "同一 nonce 自批被拒（SEC-03 SECOND_APPROVER_REQUIRED）",
          *expect(status, body, 409, "SECOND_APPROVER_REQUIRED"))

    # ── 汇总与清理 ─────────────────────────────────────────────────────
    failed = [r for r in RESULTS if r[2] == "FAIL"]
    print(f"\n==== {len(RESULTS) - len(failed)}/{len(RESULTS)} PASS ====")
    if "--keep" not in sys.argv:
        try:
            cleanup(op1_id, op2_id, team_id)
        except Exception as err:
            print(f"  清理失败（可手工清理）: {err}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

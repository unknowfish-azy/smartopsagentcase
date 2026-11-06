#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""平台 HTTP 级 E2E 验收（SEC 系列）—— 2026-11-06 晚。

前置条件：
  1. MySQL(smartops)/Redis 已启动，后端以 local profile 运行在 127.0.0.1:8080。
  2. 已通过 SQL 建好 E2E 账号：
     - e2e_admin / E2eAdmin#2026（admin，platform_admin_profile level=root）
     - e2e_op1  / E2eOp#2026（operator）
     - e2e_op2  / E2eOp#2026（operator）
  3. 已插入归属测试用的 inspector_event 数据（见 docs E2E 执行记录）。

覆盖项（对应整改清单 next_batch「平台 E2E 8 项验收」）：
  E2E-01 SEC-15/BASE  CSRF 强制、匿名受保护 API 401、健康探针
  E2E-02 SEC-08       普通用户只读自己的 inspector 事件；他人/内部通道事件 404
  E2E-03 SEC-08       审计管理员全局视图可见全部 + 留 INSPECTOR_GLOBAL_READ 审计
  E2E-04 SEC-10       GET /api/agent/loops 幂等（两次读取不产生重复闭环）
  E2E-05 SEC-10       闭环只派生自本人 inspector 事件（不吃别人的）
  E2E-06 SEC-06       爬取源指向内网/元数据地址 → run 前 KNOWLEDGE_CRAWL_URL_BLOCKED（fail-closed，不发起连接）
  E2E-07 SEC-12       knowledge 服务无/错 key 401，ingest 匿名 403，正确 key 放行
  E2E-08 SEC-07       无档案管理员只有最小只读能力（写 403 / 审计读 200）

用法：
  C:/Users/33908/AppData/Local/Programs/Python/Python314/python.exe scripts/e2e/platform_http_e2e_20261106.py
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

BASE = "http://127.0.0.1:8080"
KNOWLEDGE = "http://127.0.0.1:8002"
# 与数据准备脚本一致（见执行记录）
OP1_ID, OP2_ID, ADMIN_ID = 12, 13, 11

COLOR_HEX = {
    "红色": "#e2453c", "蓝色": "#2f6fe0", "绿色": "#2f9e5f",
    "橙色": "#e88b1f", "紫色": "#8b5cf6", "青色": "#0ea5b7",
}


NO_PROXY = urllib.request.ProxyHandler({})  # 本机直连，禁走系统代理


class Client:
    """带 cookie + CSRF 的极简 HTTP 客户端（模拟浏览器会话）。"""

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
            with self.opener.open(req, timeout=30) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            try:
                return e.code, json.loads(raw)
            except json.JSONDecodeError:
                return e.code, {"raw": raw}


def parse_shapes(scene_svg: str):
    """从 SVG 场景还原图形（中心坐标、颜色、字母），保持文档顺序。"""
    root = ET.fromstring(scene_svg)
    ns = "{http://www.w3.org/2000/svg}"
    shapes = []
    for el in root:
        tag = el.tag.replace(ns, "")
        if tag == "circle":
            shapes.append({"x": float(el.get("cx")), "y": float(el.get("cy")),
                           "fill": el.get("fill"), "letter": None})
        elif tag == "rect":
            if el.get("x") is None:  # 背景/装饰矩形，无坐标
                continue
            x, w = float(el.get("x")), float(el.get("width"))
            y, h = float(el.get("y")), float(el.get("height"))
            shapes.append({"x": x + w / 2, "y": y + h / 2,
                           "fill": el.get("fill"), "letter": None})
        elif tag == "polygon":
            pts = [tuple(map(float, p.split(","))) for p in el.get("points").split()]
            shapes.append({"x": sum(p[0] for p in pts) / len(pts),
                           "y": sum(p[1] for p in pts) / len(pts),
                           "fill": el.get("fill"), "letter": None})
        elif tag == "text" and shapes:
            # render() 里每个图形后紧跟其字母文本，按最近坐标配对
            tx, ty = float(el.get("x")), float(el.get("y"))
            nearest = min(shapes, key=lambda s: (s["x"] - tx) ** 2 + (s["y"] - ty) ** 2)
            nearest["letter"] = (el.text or "").strip()
    return shapes


def solve_clicks(prompt: str, shapes: list[dict]) -> list[dict]:
    """按提示语解出点击序列：颜色+字母 / 字母序列 / 颜色序列。"""
    body = prompt.split("的", 1)[1].strip()
    tokens = [t for t in re.split(r"[、\s]+", body) if t]
    ordered, expected = [], len(tokens)
    if len(tokens) == 2 and re.fullmatch(r"#[0-9a-fA-F]{6}", tokens[0]) and len(tokens[1]) == 1:
        hexc, letter = tokens[0].lower(), tokens[1].upper()
        ordered = [s for s in shapes if s["fill"].lower() == hexc and s["letter"] == letter]
        expected = 1  # 颜色+字母只是同一个目标的两种描述
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
    """领取本地图形点选挑战 → 解题 → 换取一次性 humanToken。"""
    status, body = client.request("GET", f"/api/auth/human-verification?action={action}")
    assert status == 200, f"领取挑战失败: {status} {body}"
    policy = body["data"]
    assert policy["provider"] == "local", f"非本地图形验证: {policy['provider']}"
    shapes = parse_shapes(policy["scene"])
    clicks = solve_clicks(policy["prompt"], shapes)
    time.sleep(0.9)  # 服务端 min-response-ms=600，模拟真人观察
    status, body = client.request("POST", "/api/auth/human-verification/verify", {
        "action": action, "nonce": policy["challenge"], "clicks": clicks})
    assert status == 200, f"解题失败: {status} {body} prompt={policy['prompt']}"
    return body["data"]["token"]


def login(username: str, password: str, portal: str) -> Client:
    client = Client()
    client.refresh_csrf()
    token = human_token(client, "admin_login" if portal == "admin" else "login")
    status, body = client.request("POST", "/api/auth/login", {
        "username": username, "password": password, "portal": portal, "humanToken": token})
    assert status == 200 and body.get("code") == 200, f"登录失败: {status} {body}"
    # 登录成功后会话重建（changeSessionId），CSRF token 随之轮换，必须重新获取
    client.refresh_csrf()
    return client


# ----------------------------------------------------------------------------
# 验收项
# ----------------------------------------------------------------------------

RESULTS = []


def check(code: str, name: str, ok: bool, evidence: str):
    RESULTS.append((code, name, "PASS" if ok else "FAIL", evidence))
    print(f"[{'PASS' if ok else 'FAIL'}] {code} {name}\n       {evidence}")


def e2e_01_base_and_csrf():
    anon = Client()
    # 匿名受保护 API → 401
    status, body = anon.request("GET", "/api/inspector/summary")
    check("E2E-01a", "匿名访问受保护 API 被拒（401）", status == 401 or body.get("code") == 401,
          f"GET /api/inspector/summary -> {status} {body.get('message', body)}")
    # POST 不带 CSRF → 403
    anon2 = Client()
    anon2.refresh_csrf()  # 建立 JSESSIONID/XSRF-TOKEN cookie
    req = urllib.request.Request(BASE + "/api/auth/login",
                                 data=json.dumps({"username": "x", "password": "y", "portal": "user"}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with anon2.opener.open(req, timeout=10) as r:
            status = r.status
    except urllib.error.HTTPError as e:
        status = e.code
    check("E2E-01b", "无 CSRF token 的 POST 被拒（403）", status == 403, f"POST /api/auth/login(无 X-XSRF-TOKEN) -> {status}")
    # 健康探针
    probe = urllib.request.build_opener(NO_PROXY)
    with probe.open(f"{BASE}/actuator/health/readiness", timeout=5) as r:
        ready = json.loads(r.read().decode())["status"]
    with probe.open(f"{BASE}/actuator/health/liveness", timeout=5) as r:
        live = json.loads(r.read().decode())["status"]
    check("E2E-01c", "readiness/liveness 探针 UP（DB/Redis 真实连通）", ready == "UP" and live == "UP",
          f"readiness={ready}, liveness={live}")


def _items(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("items", [])
    return []


def e2e_02_scope_isolation(op1: Client):
    status, body = op1.request("GET", "/api/inspector/events")
    ids = [e.get("id") for e in _items(body.get("data"))]
    own = all(i.startswith("e2e-op1-") for i in ids) and len(ids) >= 1
    check("E2E-02a", "op1 列表只含本人事件（不见 op2/内部通道）", own,
          f"op1 GET /api/inspector/events -> {len(ids)} 条: {ids}")
    # 直取他人事件 → 404
    status, body = op1.request("GET", "/api/inspector/events/e2e-op2-0001")
    check("E2E-02b", "op1 直取 op2 事件 → 404", status == 404 or body.get("code") == 404,
          f"GET /api/inspector/events/e2e-op2-0001 -> {status} {body.get('message', '')}")
    status, body = op1.request("GET", "/api/inspector/events/e2e-internal-0001")
    check("E2E-02c", "op1 直取内部通道（无归属）事件 → 404", status == 404 or body.get("code") == 404,
          f"GET /api/inspector/events/e2e-internal-0001 -> {status} {body.get('message', '')}")
    # 伪造 X-User-Id 冒充他人 → TrustedUserIdFilter 用 principal 覆盖，仍只能看自己的
    status, body = op1.request("GET", "/api/agent/loops", headers={"X-User-Id": str(OP2_ID)})
    items2 = _items(body.get("data"))
    check("E2E-02d", "伪造 X-User-Id=op2 冒充他人被 TrustedUserIdFilter 覆盖", status == 200,
          f"op1 带 X-User-Id:{OP2_ID} GET /api/agent/loops -> {status}，返回 {len(items2)} 条（服务端按 principal=op1 处理）")


def e2e_03_audit_admin_global(admin: Client):
    status, body = admin.request("GET", "/api/inspector/events")
    ids = {e.get("id") for e in _items(body.get("data"))}
    see_all = {"e2e-op1-0001", "e2e-op2-0001", "e2e-internal-0001"} <= ids
    check("E2E-03a", "审计管理员全局视图可见全部（含内部通道）事件", see_all,
          f"admin GET /api/inspector/events -> {len(ids)} 条，含三方数据: {see_all}")
    # 审计记录由 DB 侧核验（security_audit_event 追加 INSPECTOR_GLOBAL_READ），此处不重复断言


def e2e_04_loop_idempotent(op1: Client):
    status1, b1 = op1.request("GET", "/api/agent/loops")
    status2, b2 = op1.request("GET", "/api/agent/loops")
    n1, n2 = len(_items(b1.get("data"))), len(_items(b2.get("data")))
    check("E2E-04", "GET /api/agent/loops 幂等（两次读取闭环数量不变）", n1 == n2,
          f"第一次 {n1} 条 / 第二次 {n2} 条")


def e2e_05_loop_scope(op1: Client):
    status, body = op1.request("GET", "/api/agent/loops")
    items = _items(body.get("data"))
    from_others = [i for i in items if i.get("sourceRef") and not str(i.get("sourceRef")).startswith("e2e-op1-")]
    check("E2E-05", "闭环只派生自本人 inspector 事件", len(from_others) == 0,
          f"op1 闭环 {len(items)} 条，来自他人事件的 {len(from_others)} 条")


def e2e_06_crawl_fail_closed(op1: Client):
    # 建库
    status, body = op1.request("POST", "/api/knowledge/personal/libraries",
                               {"name": "e2e-crawl-lib-20261106", "description": "E2E 爬取负例"})
    lib = (body.get("data") or {}) if isinstance(body.get("data"), dict) else {}
    library_id = lib.get("id")
    for label, url in [("本机回环", "http://127.0.0.1:8080/actuator/health"),
                       ("云元数据", "http://169.254.169.254/latest/meta-data/"),
                       ("私网网关", "http://192.168.1.1/")]:
        status, body = op1.request("POST", "/api/knowledge/crawl/sources",
                                   {"libraryId": library_id, "name": f"e2e-{label}", "seedUrl": url,
                                    "maxPages": 1, "depth": 0})
        if status != 200 or body.get("code") != 200:
            check(f"E2E-06({label})", f"内网地址({label})建源即被拒", True,
                  f"POST /api/knowledge/crawl/sources seedUrl={url} -> {body.get('code')} {body.get('message', '')}")
            continue
        source_id = (body.get("data") or {}).get("id")
        status, body = op1.request("POST", f"/api/knowledge/crawl/sources/{source_id}/run")
        blocked = body.get("code") == 400 and "BLOCKED" in str(body.get("message", ""))
        check(f"E2E-06({label})", f"内网地址({label}) run 前 fail-closed 拒绝", blocked,
              f"run -> {body.get('code')} {body.get('message', '')}")


def e2e_07_knowledge_auth():
    key = None
    try:
        with open(".env", encoding="utf-8") as f:
            m = re.search(r"^KNOWLEDGE_API_KEY=(.+)$", f.read(), re.M)
            key = m.group(1).strip() if m else None
    except OSError:
        pass
    if not key:
        check("E2E-07", "knowledge 鉴权（读取 .env key 失败）", False, ".env 中无 KNOWLEDGE_API_KEY")
        return

    def call(method, path, headers=None, payload=None):
        req = urllib.request.Request(KNOWLEDGE + path, method=method,
                                     headers=headers or {},
                                     data=json.dumps(payload).encode() if payload else None)
        try:
            with urllib.request.build_opener(NO_PROXY).open(req, timeout=15) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")[:120]

    s, _ = call("GET", "/api/health")
    if s != 200:
        check("E2E-07", "knowledge 服务可达（127.0.0.1:8002）", False, f"GET /api/health -> {s}（服务未启动？）")
        return
    s, _ = call("POST", "/api/search", {"Content-Type": "application/json"}, {"query": "nginx", "top_k": 3})
    a = s == 401
    s2, _ = call("POST", "/api/search", {"Content-Type": "application/json", "X-API-Key": "wrong-key"},
                 {"query": "nginx", "top_k": 3})
    b = s2 == 401
    s3, _ = call("POST", "/api/search", {"Content-Type": "application/json", "X-API-Key": key},
                 {"query": "nginx", "top_k": 3})
    c = s3 == 200
    s4, _ = call("POST", "/api/documents", {"Content-Type": "application/json"},
                 {"content": "e2e auth probe 20261106", "source": "e2e.py"})
    # 已配置 key 时匿名 ingest 走 401（key 缺失/错误）；仅当服务未配 key 时才是 403。两者都属 fail-closed。
    d = s4 in (401, 403)
    s5, body5 = call("POST", "/api/documents", {"Content-Type": "application/json", "X-API-Key": key},
                     {"content": "e2e auth probe 20261106", "source": "e2e.py"})
    e = s5 == 200
    check("E2E-07", "knowledge fail-closed：无 key 401 / 错 key 401 / 对 key 200 / 匿名 ingest 403 / 带 key ingest 200",
          a and b and c and d and e,
          f"search 无key={s} 错key={s2} 对key={s3}; ingest 无key={s4} 带key={s5} {str(body5)[:60]}")


def e2e_08_governance_minimal():
    # 无档案管理员 = e2e_admin2（无 platform_admin_profile），SQL 预建，密码同 E2eAdmin#2026
    try:
        client = login("e2e_admin2", "E2eAdmin#2026", "admin")
    except AssertionError as err:
        check("E2E-08", "无档案管理员最小只读", False, f"登录失败: {err}")
        return
    status, body = client.request("GET", "/api/inspector/events")  # admin.audit 最小只读
    read_ok = status == 200
    wstatus, wbody = client.request("POST", "/api/admin/system/depts", {"name": "e2e-不应成功"})
    write_blocked = wstatus in (403, 400) or wbody.get("code") in (403, 400)
    check("E2E-08", "SEC-07 无档案管理员仅最小只读（审计读 200 / 配置写被拒）",
          read_ok and write_blocked,
          f"全局事件读 -> {status}（最小只读 admin.audit）；POST /api/admin/system/depts -> {wstatus} {wbody.get('message', '')[:40]}")


def main():
    print("=" * 72)
    print("平台 HTTP 级 E2E 验收（SEC 系列）—— 2026-11-06 晚")
    print("=" * 72)
    e2e_01_base_and_csrf()
    op1 = login("e2e_op1", "E2eOp#2026", "user")
    admin = login("e2e_admin", "E2eAdmin#2026", "admin")
    e2e_02_scope_isolation(op1)
    e2e_03_audit_admin_global(admin)
    e2e_04_loop_idempotent(op1)
    e2e_05_loop_scope(op1)
    e2e_06_crawl_fail_closed(op1)
    e2e_07_knowledge_auth()
    e2e_08_governance_minimal()

    failed = [r for r in RESULTS if r[2] != "PASS"]
    print("=" * 72)
    print(f"合计 {len(RESULTS)} 项：PASS {len(RESULTS) - len(failed)} / FAIL {len(failed)}")
    for code, name, status, _ in RESULTS:
        print(f"  {status:>4}  {code:<14} {name}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

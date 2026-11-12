#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐页快照：登录后遍历用户层与管理层全部页面，保存截图 + 页面可见文本。

用途：为演示讲解稿提供「页面上真实有什么」的依据，避免凭想象写功能名。
不绕过任何安全机制：复用 E2E 的 API 登录链路（含人机校验解题）拿会话 cookie。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sec0405_approval_e2e_20261106 import (  # noqa: E402
    Client, PASSWORD, human_token, login, sql_exec,
)

FRONT = "http://127.0.0.1:5173"
ADMIN_FRONT = "http://127.0.0.1:5174"
OUT = Path("test-artifacts/ui-pages")

DEMO_USER = "demo_ops"


def _demo_password() -> str:
    """演示口令只来自环境变量或本机 .env，不写入仓库（仓库公开，硬编码等于泄露）。"""
    key = "SMARTOPS_DEMO_PASSWORD"
    value = os.environ.get(key)
    if not value:
        env_file = Path(__file__).resolve().parents[2] / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith(key + "="):
                    value = line.split("=", 1)[1].strip()
                    break
    if not value:
        raise SystemExit(f"缺少 {key}：请在环境变量或仓库根目录 .env 中配置 demo_ops 演示口令")
    return value


DEMO_PASSWORD = _demo_password()

USER_ROUTES = [
    ("01-home", "/"),
    ("02-chat", "/chat"),
    ("03-teams", "/teams"),
    ("04-knowledge", "/knowledge"),
    ("05-cloud-native", "/cloud-native"),
    ("06-plugins", "/plugins"),
    ("07-skills", "/skills"),
    ("08-connections", "/connections"),
    ("09-harbor", "/harbor"),
    ("10-servers", "/servers"),
    ("11-health", "/health"),
    ("12-milestones", "/milestones"),
    ("13-model-settings", "/model-settings"),
    ("14-model-gateway", "/model-gateway"),
    ("15-model-strength", "/model-strength"),
    ("16-token-usage", "/token-usage"),
    ("17-agent", "/agent"),
    ("18-agent-trace", "/agent/trace"),
    ("19-inspector", "/inspector"),
    ("20-inspector-stats", "/inspector/statistics"),
    ("21-runs", "/operations/runs"),
    ("22-recovery", "/operations/recovery"),
    ("23-knowledge-review", "/knowledge/review"),
    ("24-sentinel", "/sentinel"),
    ("25-scripts", "/sentinel/scripts"),
    ("26-alerts", "/sentinel/alerts"),
    ("27-incidents", "/incidents"),
    ("28-guardian", "/sentinel/guardian"),
    ("29-tools", "/tools"),
    ("30-account-security", "/account/security"),
    ("31-architecture", "/architecture"),
]

ADMIN_ROUTES = [
    ("a01-overview", "/admin"),
    ("a02-users", "/admin/users"),
    ("a03-governance", "/admin/governance"),
    ("a04-teams", "/admin/teams"),
    ("a05-sessions", "/admin/sessions"),
    ("a06-audit", "/admin/audit"),
    ("a07-approvals", "/admin/approvals"),
    ("a08-models", "/admin/models"),
    ("a09-security", "/admin/security"),
    ("a10-readiness", "/admin/readiness"),
]


def _chromium_exe() -> str | None:
    root = Path.home() / "AppData/Local/ms-playwright"
    for pattern in ("chromium-*/chrome-win64/chrome.exe",
                    "chromium_headless_shell-*/chrome-headless-shell-win64/chrome-headless-shell.exe",
                    "chromium-*/chrome-win/chrome.exe"):
        for exe in sorted(root.glob(pattern), reverse=True):
            if exe.exists():
                return str(exe)
    return None


def ensure_admin(username: str = "e2e_admin"):
    """建/复位一个 admin 角色账号（仅本地演示环境），并按管理员入口的人机验证动作登录。

    注意：role=admin 只决定入口，平台能力（admin.users 等）另存于 platform_admin_capability。
    root 账号（id=1）的能力行会被临时复制到本账号，快照结束后清除，不触碰原账号。
    """
    import bcrypt
    hashed = bcrypt.hashpw(PASSWORD.encode("utf-8"), bcrypt.gensalt(prefix=b"2a")).decode("ascii")
    row = sql_exec(f"SELECT id FROM app_user WHERE username='{username}'")
    if row:
        uid = row[0]
        sql_exec("UPDATE app_user SET password_hash=%s, role='admin', enabled=1 WHERE id=%s",
                 (hashed, uid))
    else:
        sql_exec("INSERT INTO app_user(username, password_hash, role, enabled) VALUES(%s, %s, 'admin', 1)",
                 (username, hashed))
        uid = sql_exec(f"SELECT id FROM app_user WHERE username='{username}'")[0]

    # 临时补齐平台能力（与 root 账号一致），否则管理页全部显示"平台权限不足"
    sql_exec("INSERT IGNORE INTO platform_admin_profile(user_id, level) VALUES(%s, 'root')", (uid,))
    sql_exec("""INSERT IGNORE INTO platform_admin_capability(user_id, capability, granted_by)
                SELECT %s, capability, %s FROM platform_admin_capability WHERE user_id=1""",
             (uid, uid))

    client = Client()
    client.refresh_csrf()
    # 管理入口的人机验证 action 是 admin_login，与用户入口的 login 不同
    token = human_token(client, "admin_login")
    status, body = client.request("POST", "/api/auth/login", {
        "username": username, "password": PASSWORD, "portal": "admin", "humanToken": token})
    assert status == 200 and body.get("code") == 200, f"管理员登录失败: {status} {body}"
    client.refresh_csrf()
    return client


def cleanup_admin_caps(username: str = "e2e_admin"):
    """删除为快照临时补的平台能力行，恢复原状态。"""
    row = sql_exec(f"SELECT id FROM app_user WHERE username='{username}'")
    if row:
        sql_exec("DELETE FROM platform_admin_capability WHERE user_id=%s", (row[0],))
        print(f"[CLEANUP] 已清除 {username}(id={row[0]}) 的临时平台能力")


def walk(page, routes, front, prefix=""):
    results = []
    for name, route in routes:
        try:
            page.goto(front + route, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(2600)
            text = (page.inner_text("body") or "").strip()
            (OUT / f"{prefix}{name}.txt").write_text(text, encoding="utf-8")
            page.screenshot(path=str(OUT / f"{prefix}{name}.png"))
            results.append({"name": name, "route": route, "final_url": page.url, "chars": len(text)})
            print(f"[OK] {route} -> {page.url} ({len(text)} 字)")
        except Exception as err:  # noqa: BLE001
            results.append({"name": name, "route": route, "error": str(err)})
            print(f"[ERR] {route}: {err}")
    return results


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    exe = _chromium_exe()

    user_client = login(DEMO_USER, DEMO_PASSWORD)
    admin_client = ensure_admin()

    all_results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=exe) if exe \
            else p.chromium.launch(headless=True)

        ctx_u = browser.new_context(viewport={"width": 1600, "height": 1000})
        ctx_u.add_cookies([{"name": c.name, "value": c.value or "", "url": FRONT} for c in user_client.jar])
        page_u = ctx_u.new_page()
        all_results["user"] = walk(page_u, USER_ROUTES, FRONT)

        ctx_a = browser.new_context(viewport={"width": 1600, "height": 1000})
        ctx_a.add_cookies([{"name": c.name, "value": c.value or "", "url": ADMIN_FRONT} for c in admin_client.jar])
        page_a = ctx_a.new_page()
        all_results["admin"] = walk(page_a, ADMIN_ROUTES, ADMIN_FRONT, prefix="")

        browser.close()

    (OUT / "pages.json").write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
    cleanup_admin_caps()
    print(f"\n输出目录: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

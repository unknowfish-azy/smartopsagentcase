#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""前端 UI 全链路走通（Playwright）。

做法：不走 UI 登录表单（有图形点选人机验证），而是复用 E2E 的 API 登录链路拿到
会话 cookie，注入浏览器后逐页访问 —— 这样验证的是「登录后的真实前端渲染与接口调用」，
不绕过任何安全机制。

输出：test-artifacts/ui-walkthrough/<route>.png + 控制台错误/接口失败汇总；
退出码 0 表示全部页面无 JS 异常、无 >=400 的 /api 响应、页面有可见内容。
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sec0405_approval_e2e_20261106 import ensure_user  # noqa: E402

FRONT = "http://127.0.0.1:5173"
USER = "e2e_ui"  # 密码由 ensure_user 内部常量统一（SQL+bcrypt 建号兜底）
OUT = Path("test-artifacts/ui-walkthrough")

ROUTES = [
    ("dashboard", "/"),
    ("chat", "/chat"),
    ("servers", "/servers"),
    ("connections", "/connections"),
    ("inspector", "/inspector"),
    ("knowledge", "/knowledge"),
    ("teams", "/teams"),
    ("sentinel", "/sentinel"),
    ("incidents", "/incidents"),
    ("operation-runs", "/operations/runs"),
    ("model-settings", "/model-settings"),
    ("account-security", "/account/security"),
]


def _chromium_exe() -> str | None:
    """复用本机已装 chromium（Python 版 playwright 与 node 版 revision 常不一致）。"""
    root = Path.home() / "AppData/Local/ms-playwright"
    for pattern in ("chromium-*/chrome-win64/chrome.exe",
                    "chromium_headless_shell-*/chrome-headless-shell-win64/chrome-headless-shell.exe",
                    "chromium-*/chrome-win/chrome.exe"):
        for exe in sorted(root.glob(pattern), reverse=True):
            if exe.exists():
                return str(exe)
    return None


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    client = ensure_user(USER)
    cookies = [
        {"name": c.name, "value": c.value or "", "url": FRONT}
        for c in client.jar
    ]
    print(f"[INFO] 会话 cookie: {[c['name'] for c in cookies]}")

    exe = _chromium_exe()
    print(f"[INFO] chromium: {exe or '(playwright 默认)'}")

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=exe) if exe \
            else p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_cookies(cookies)
        page = ctx.new_page()

        console_errors: list[str] = []
        page_errors: list[str] = []
        api_failures: list[str] = []
        page.on("console", lambda m: console_errors.append(f"{m.type}: {m.text}")
                if m.type == "error" else None)
        page.on("pageerror", lambda e: page_errors.append(str(e)))
        page.on("response", lambda r: api_failures.append(f"{r.status} {r.url}")
                if "/api/" in r.url and r.status >= 400 else None)

        for name, route in ROUTES:
            console_errors.clear()
            page_errors.clear()
            api_failures.clear()
            started = time.time()
            try:
                page.goto(FRONT + route, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(2500)  # 等首屏接口与异步组件
                text = (page.inner_text("body") or "").strip()
                shot = OUT / f"{name.replace('/', '_')}.png"
                page.screenshot(path=str(shot), full_page=False)
                url = page.url
                ok = (not page_errors) and (not api_failures) and len(text) > 40
                results.append({
                    "name": name, "route": route, "final_url": url,
                    "ok": ok, "text_len": len(text), "shot": str(shot),
                    "page_errors": list(page_errors),
                    "api_failures": list(api_failures),
                    "console_errors": [c for c in console_errors if "favicon" not in c][:5],
                    "seconds": round(time.time() - started, 1),
                })
                flag = "PASS" if ok else "FAIL"
                print(f"[{flag}] {route} -> {url} ({len(text)} 字, {results[-1]['seconds']}s)")
                for err in page_errors:
                    print(f"        JS 异常: {err[:160]}")
                for fail in api_failures[:4]:
                    print(f"        接口失败: {fail[:160]}")
            except Exception as err:  # noqa: BLE001
                results.append({"name": name, "route": route, "ok": False,
                                "page_errors": [f"导航失败: {err}"], "api_failures": []})
                print(f"[FAIL] {route} 导航异常: {err}")

        browser.close()

    failed = [r for r in results if not r["ok"]]
    (OUT / "report.json").write_text(
        json.dumps({"user": USER, "base": FRONT, "results": results},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n==== {len(results) - len(failed)}/{len(results)} 页面通过 ====")
    for r in failed:
        print(f"  FAIL {r['route']}: {r.get('page_errors') or r.get('api_failures')}")
    print(f"报告: {OUT / 'report.json'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

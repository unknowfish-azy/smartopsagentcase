#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UI 层 AI 对话端到端：浏览器内发一条真实运维问题，等 Ollama 模型回答。"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sec0405_approval_e2e_20261106 import ensure_user  # noqa: E402
from ui_walkthrough_playwright import _chromium_exe  # noqa: E402

FRONT = "http://127.0.0.1:5173"
USER = "e2e_ui"
SHOT = Path("test-artifacts/ui-walkthrough/chat-live.png")


def main() -> int:
    client = ensure_user(USER)
    cookies = [{"name": c.name, "value": c.value or "", "url": FRONT} for c in client.jar]
    exe = _chromium_exe()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=exe)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_cookies(cookies)
        page = ctx.new_page()
        page.goto(FRONT + "/chat", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2500)

        box = page.get_by_placeholder("描述你要完成的运维目标…")
        if box.count() == 0:
            box = page.locator("textarea").first
        box.fill("用一句话说明 Linux 里如何查看占用 CPU 最高的进程")
        box.press("Enter")
        print("[INFO] 消息已发送，等待模型回答…")
        page.wait_for_timeout(45000)
        text = page.inner_text("body")
        # 回答特征：UI 渲染的执行痕迹/模型标注/含命令建议的回答文本
        markers = [ln.strip() for ln in text.splitlines()
                   if (("运行步骤" in ln or "参考来源" in ln or "qwen" in ln.lower()
                        or ("top" in ln.lower() and "进程" in ln))
                       and len(ln.strip()) > 6)]
        page.screenshot(path=str(SHOT))
        browser.close()
        print(f"[INFO] 回答特征行: {markers[:5]}")
        print(f"[INFO] 截图: {SHOT}")
        if markers:
            print("[PASS] UI 对话链路返回了模型回答")
            return 0
        print("[FAIL] 45s 内未见模型回答特征")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

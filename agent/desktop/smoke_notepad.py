"""DH-08 真机冒烟：只碰记事本，每步都产 receipt。

四步：
1. 用临时文件启动记事本 → observe → 断言元素树非空
2. type("SmartOps desktop hand smoke test") → 回读 UIA value 校验
3. Ctrl+S 直接保存（文件已绑定路径，不弹另存为）→ 校验磁盘内容
4. Ctrl+W 关闭 → 等待窗口消失
最后打印 VERIFIED / UNVERIFIED / REJECTED 统计，不为零就以非零码退出。

给记事本一个明确的临时文件，是为了绕开"另存为"对话框：
Windows 11 记事本会恢复上次会话/已保存路径，未命名文档按 Ctrl+S 才弹框，
行为不确定；预绑定文件后 Ctrl+S 永远是静默保存，冒烟结果可复现。

刻意做的"笨"的事：
- 每一步都重新 observe 再动作——别信 pywinauto 的缓存句柄，
  窗口切换 / 控件刷新会让旧 handle 失效；
- 用剪贴板 + Ctrl+V 而不是 type_keys，中文可靠；
- 不在脚本里做"如果 Ctrl+S 弹了什么对话框"的复杂分支，
  只记录 receipt；真碰到边界交给人看轨迹。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

_RESULT_DIR = Path("agent/desktop/shots")
_LEDGER_PATH = Path("agent/desktop/smoke_receipts.jsonl")
_RUN_ID = "smoke-notepad"
_SMOKE_TEXT = "SmartOps desktop hand smoke test 2026-11-19"
_MAX_WAIT_SEC = 10


def _import_windows_driver():
    from agent.desktop.driver_windows import WindowsDriver  # noqa: WPS433

    available, reason = WindowsDriver.available()
    if not available:
        raise SystemExit(f"WindowsDriver 不可用，跳过冒烟：{reason}")
    return WindowsDriver()


def _wait_for(predicate, description: str, timeout: float = _MAX_WAIT_SEC) -> Any:
    deadline = time.perf_counter() + timeout
    last_error: Exception | None = None
    while time.perf_counter() < deadline:
        try:
            result = predicate()
            if result:
                return result
        except Exception as exc:  # noqa: BLE001 - 等待期间允许瞬时异常
            last_error = exc
        time.sleep(0.2)
    raise TimeoutError(f"等待超时：{description}（最后错误：{last_error}）")


def _launch_notepad(driver, save_path: Path) -> str:
    """用目标文件启动记事本（Ctrl+S 会静默保存），返回 window_id。"""
    # 先落一个空文件，记事本就绑定到这个路径，不会弹"另存为"。
    save_path.parent.mkdir(parents=True, exist_ok=True)
    save_path.write_text("", encoding="utf-8")

    subprocess.Popen(["notepad.exe", str(save_path)])
    hwnd = _wait_for(
        lambda: next(
            (
                w.window_id
                for w in driver.list_windows()
                if w.process_name.lower().endswith("notepad.exe")
                and save_path.name in w.window_title
            ),
            None,
        ),
        "记事本窗口出现",
    )
    print(f"[smoke] 启动记事本 {hwnd}（{save_path.name}）")
    return hwnd


def _tab_closed(window_id: str, document_name: str) -> bool:
    """记事本是单窗口多标签：Ctrl+W 关的是标签页，窗口可能还开着别的页。"""

    import win32gui  # noqa: WPS433

    hwnd = int(window_id.removeprefix("hwnd-"))
    if not win32gui.IsWindow(hwnd):
        return True
    return document_name not in (win32gui.GetWindowText(hwnd) or "")


def _ensure_notepad(save_path: Path) -> tuple[Any, str]:
    """启动记事本并返回 (driver, window_id)。"""
    driver = _import_windows_driver()
    return driver, _launch_notepad(driver, save_path)


def _find_edit_element(hand, window_id: str) -> str:
    """在观测里挑一个 edit 控件（记事本的主编辑区）。"""
    obs = hand.driver.observe(window_id)
    for element in obs.elements:
        if element.role in ("edit", "text", "text field", "document"):
            return element.element_id
    raise RuntimeError(f"记事本观测到 {len(obs.elements)} 个元素，但找不到 edit 控件")


def _read_notepad_text(window_id: str) -> str:
    """按窗口句柄直连 UIA 读编辑区文本。

    不走全局窗口枚举（`Desktop().windows()` 在某些会话里会阻塞），也不读
    `element_info.name`——记事本的正文在 ValuePattern 里，Name 只是控件名。
    """
    from pywinauto import Application  # noqa: WPS433

    handle = int(window_id.removeprefix("hwnd-"))
    window = Application(backend="uia").connect(handle=handle).window(handle=handle)

    chunks: list[str] = []
    for control in window.descendants():
        control_type = (control.element_info.control_type or "").lower()
        if control_type not in ("edit", "document"):
            continue
        try:
            chunks.append(control.get_value() or "")
        except Exception:  # noqa: BLE001 - Document 控件没有 ValuePattern
            pass
        try:
            chunks.append(control.window_text() or "")
        except Exception:  # noqa: BLE001
            pass
    return "\n".join(chunks)


def _notepad_has_text(hand, window_id: str, expected: str) -> bool:
    """读记事本 UIA value 里有没有那段 smoke 字符串。"""
    try:
        return expected in _read_notepad_text(window_id)
    except Exception:
        return False


def main() -> int:
    print("=" * 60)
    print("SmartOpsAgent 桌面手真机冒烟（记事本）")
    print("=" * 60)

    result_dir = _RESULT_DIR / _RUN_ID
    result_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = result_dir / "receipts.jsonl"

    # 按需导入，避免 Linux / 无 pywinauto 环境 import 崩溃
    from agent.desktop.gateway import DesktopGateway
    from agent.desktop.policy import DesktopPolicy, WindowRule
    from agent.desktop.receipts import DesktopReceiptLog, ShotStore
    from agent.tools.desktop import DesktopHand

    # 策略：输入组开启（冒烟就是测输入）；窗口白名单只放 notepad.exe
    policy = DesktopPolicy(
        input_group_enabled=True,
        window_allowlist=(
            WindowRule(
                process="notepad.exe",
                title_regex=".*",
                allowed_roles=frozenset(
                    {"button", "edit", "text", "menu", "menuitem", "document"}
                ),
            ),
        ),
    )
    gateway = DesktopGateway(policy)
    shots = ShotStore(result_dir)
    receipts = DesktopReceiptLog(ledger_path)

    workdir = Path(tempfile.mkdtemp(prefix="smartops-dh08-"))
    # 唯一文件名：记事本会恢复旧标签，重名会让"标签页关闭"判断失真。
    save_path = workdir / f"dh08_smoke_{int(time.time())}.txt"

    driver, window_id = _ensure_notepad(save_path)
    hand = DesktopHand(
        driver,
        gateway,
        run_id=_RUN_ID,
        shot_store=shots,
        receipt_log=receipts,
    )

    verdict_counts: dict[str, int] = {}
    input_unverified = 0
    smoke_ok = True

    def _count(receipt: dict[str, Any]) -> None:
        nonlocal input_unverified
        verdict = receipt.get("verdict", "MISSING")
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
        # observe 天然没有 after 截图，判 UNVERIFIED 是契约要求；
        # 只有输入类动作（click/type/key）必须 VERIFIED。
        if receipt.get("action") != "observe" and verdict != "VERIFIED":
            input_unverified += 1

    try:
        # ---- Step 1: observe ----
        print("\n[1/4] 观测记事本窗口 …")
        try:
            result = hand.observe(window_id)
        except ValueError:
            # 复用的窗口可能在两次枚举之间被关掉了：重开一个再观测。
            print("      复用的窗口已失效，重新启动记事本")
            window_id = _launch_notepad(driver)
            result = hand.observe(window_id)
        assert result["ok"] is True, result
        _count(result["receipt"])
        print(f"      元素 {len(result['elements'])} 个，truncated={result['truncated']}")

        # ---- Step 2: type ----
        print("\n[2/4] 输入 smoke 文本 …")
        edit_element = _find_edit_element(hand, window_id)
        result = hand.type_text(window_id, edit_element, _SMOKE_TEXT)
        _count(result["receipt"])
        assert result["ok"] is True, result
        print(f"      输入 {len(_SMOKE_TEXT)} 字符，receipt={result['receipt']['verdict']}")

        # 回读 UIA value 做独立校验
        _wait_for(
            lambda: _notepad_has_text(hand, window_id, _SMOKE_TEXT),
            "记事本回读 smoke 文本",
            timeout=5,
        )
        print("      UIA value 校验通过")

        # ---- Step 3: Ctrl+S 保存 ----
        print("\n[3/4] Ctrl+S 保存 …")
        result = hand.press_key(window_id, "ctrl+s")
        _count(result["receipt"])
        assert result["ok"] is True, result

        def _saved() -> bool:
            return _SMOKE_TEXT in save_path.read_text(encoding="utf-8", errors="replace")

        _wait_for(_saved, "保存文件写入 smoke 文本", timeout=5)
        content = save_path.read_text(encoding="utf-8", errors="replace")
        print(f"      保存文件校验通过：{save_path.name}（{len(content)} 字符）")

        # ---- Step 4: Ctrl+W 关闭 ----
        print("\n[4/4] Ctrl+W 关闭窗口 …")
        result = hand.press_key(window_id, "ctrl+w")
        _count(result["receipt"])
        assert result["ok"] is True, result

        # 文件刚保存过，Ctrl+W 不应再弹确认框；标签页没关掉就说明有对话框挡住。
        _wait_for(
            lambda: _tab_closed(window_id, save_path.name),
            "标签页关闭",
            timeout=3,
        )
        print("      标签页已关闭")

    except Exception as exc:  # noqa: BLE001 - 冒烟脚本边界，错误必须打印 + 保留轨迹
        smoke_ok = False
        print(f"\n[smoke] 失败：{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        print("\n" + "=" * 60)
        print("Receipt 统计：")
        for verdict, count in sorted(verdict_counts.items()):
            print(f"  {verdict:<12} {count}")
        print(f"\n账本：{ledger_path}")
        print(f"截图：{result_dir}")

    failed = (
        not smoke_ok
        or verdict_counts.get("REJECTED", 0) > 0
        or input_unverified > 0
        or "MISSING" in verdict_counts
    )
    if failed:
        print("\n[smoke] 有失败 / 拒绝 / 输入未验证步骤，退出码 = 1")
        return 1
    shutil.rmtree(workdir, ignore_errors=True)
    print("\n[smoke] 输入动作全部 VERIFIED，通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

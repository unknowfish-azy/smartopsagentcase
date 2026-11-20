"""DH-06 证据测试：verdict 由证据决定、截图落盘、账本只追加、digest 跨服务一致。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from agent.desktop.driver import shot_digest
from agent.desktop.driver_fake import FakeDriver
from agent.desktop.element_id import element_id
from agent.desktop.gateway import DesktopGateway
from agent.desktop.models import DesktopContractError, UiElement, WindowInfo
from agent.desktop.policy import DesktopPolicy, WindowRule
from agent.desktop.receipts import (
    DesktopReceiptLog,
    ShotStore,
    build_receipt,
    canonical_digest,
    element_diff,
    receipt_payload,
)
from agent.tools.desktop import DesktopHand, build_desktop_tools

REPO_ROOT = Path(__file__).resolve().parents[2]

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
TARGET = {"window_id": "hwnd-1", "element_id": "e" * 16}


def _element(name: str = "保存", *, enabled: bool = True) -> UiElement:
    bbox = (0, 0, 100, 30)
    return UiElement(
        element_id=element_id("hwnd-1", "button", name, bbox),
        role="button",
        name=name,
        bbox=bbox,
        enabled=enabled,
    )


class _ChangingDriver(FakeDriver):
    """点击后元素消失、画面变化，模拟真实的界面反馈。"""

    def __init__(self) -> None:
        super().__init__(
            windows=[WindowInfo("hwnd-1", "记事本", "notepad.exe")],
            elements={"hwnd-1": [_element()]},
            screenshot_bytes=b"before-png-bytes",
        )

    def click(self, window_id: str, element_id: str) -> None:
        super().click(window_id, element_id)
        self._elements[window_id] = [
            element
            for element in self._elements[window_id]
            if element.element_id != element_id
        ]
        self._shot = b"after-png-bytes"


def _hand(tmp_path: Path, driver: FakeDriver, *, input_group_enabled: bool = True) -> DesktopHand:
    policy = DesktopPolicy(
        input_group_enabled=input_group_enabled,
        window_allowlist=(
            WindowRule(
                process="notepad.exe",
                title_regex=".*",
                allowed_roles=frozenset({"button", "edit"}),
            ),
        ),
    )
    return DesktopHand(
        driver,
        DesktopGateway(policy),
        run_id="run-1",
        shot_store=ShotStore(tmp_path / "shots"),
        receipt_log=DesktopReceiptLog(tmp_path / "receipts.jsonl"),
    )


def _tool(hand: DesktopHand, name: str):
    return {tool.name: tool for tool in build_desktop_tools(hand)}[name]


# ---------------------------------------------------------------------------
# verdict 由证据决定
# ---------------------------------------------------------------------------


def test_缺_after_截图只能是_UNVERIFIED():
    receipt = build_receipt(
        run_id="run-1",
        step=1,
        action="click",
        target=TARGET,
        before_digest=DIGEST_A,
    )

    assert receipt.verdict == "UNVERIFIED"
    assert receipt.after_shot_digest is None
    assert receipt.element_diff == {}


def test_after_无任何变化也判_UNVERIFIED():
    element = _element()

    receipt = build_receipt(
        run_id="run-1",
        step=1,
        action="click",
        target=TARGET,
        before_digest=DIGEST_A,
        after_digest=DIGEST_A,
        before_elements=[element],
        after_elements=[element],
    )

    assert receipt.verdict == "UNVERIFIED"


def test_after_有变化判_VERIFIED_并记录_diff():
    element = _element()

    receipt = build_receipt(
        run_id="run-1",
        step=2,
        action="click",
        target=TARGET,
        before_digest=DIGEST_A,
        after_digest=DIGEST_B,
        before_elements=[element],
        after_elements=[],
    )

    assert receipt.verdict == "VERIFIED"
    assert receipt.after_shot_digest == DIGEST_B
    assert receipt.element_diff["disappeared"] == [element.element_id]


def test_element_diff_捕捉_enabled_翻转():
    enabled = _element(enabled=True)
    disabled = _element(enabled=False)

    diff = element_diff([enabled], [disabled])

    assert diff["changed"] == [enabled.element_id]
    assert diff["appeared"] == [] and diff["disappeared"] == []


# ---------------------------------------------------------------------------
# digest 跨服务一致
# ---------------------------------------------------------------------------


def test_digest_与_ai_service_canonical_一致():
    if str(REPO_ROOT / "ai-service") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "ai-service"))
    from app.core.canonical import canonical_digest as ai_service_digest

    payload = {"b": 1, "a": [2, {"c": None}], "z": "中文"}

    assert canonical_digest(payload) == ai_service_digest(payload)
    assert canonical_digest(payload).startswith("sha256:")


# ---------------------------------------------------------------------------
# 落盘与账本
# ---------------------------------------------------------------------------


def test_点击成功后_VERIFIED_且截图与_digest_对得上(tmp_path):
    hand = _hand(tmp_path, _ChangingDriver())

    result = _tool(hand, "desktop.click").execute(
        window_id="hwnd-1", element_id=_element().element_id
    )

    receipt = result["receipt"]
    assert receipt["verdict"] == "VERIFIED"
    before_path = Path(receipt["shots"]["before"])
    after_path = Path(receipt["shots"]["after"])
    assert before_path.exists() and after_path.exists()
    assert shot_digest(before_path.read_bytes()) == receipt["before_shot_digest"]
    assert shot_digest(after_path.read_bytes()) == receipt["after_shot_digest"]


def test_receipt_不含图片字节(tmp_path):
    hand = _hand(tmp_path, _ChangingDriver())

    result = _tool(hand, "desktop.click").execute(
        window_id="hwnd-1", element_id=_element().element_id
    )

    text = json.dumps(result["receipt"], ensure_ascii=False)
    assert "before-png-bytes" not in text
    assert "after-png-bytes" not in text
    assert "base64" not in text
    assert set(result["receipt"]) == {
        "run_id",
        "step",
        "action",
        "target",
        "before_shot_digest",
        "after_shot_digest",
        "element_diff",
        "verdict",
        "reject_reason",
        "shots",
    }


def test_拒绝也产_REJECTED_回执(tmp_path):
    hand = _hand(tmp_path, _ChangingDriver(), input_group_enabled=False)

    result = _tool(hand, "desktop.click").execute(
        window_id="hwnd-1", element_id=_element().element_id
    )

    assert result["ok"] is False
    assert result["receipt"]["verdict"] == "REJECTED"
    assert result["receipt"]["reject_reason"] == "INPUT_GROUP_DISABLED"
    assert result["receipt"]["after_shot_digest"] is None
    # 拒绝时只落 before 一张，不产生 after
    assert set(result["receipt"]["shots"]) == {"before"}


def test_急停期间的回执是_R5(tmp_path):
    hand = _hand(tmp_path, _ChangingDriver())
    hand.gateway.emergency_stop("运维按下急停")

    result = _tool(hand, "desktop.click").execute(
        window_id="hwnd-1", element_id=_element().element_id
    )

    assert result["receipt"]["verdict"] == "REJECTED"
    assert result["receipt"]["reject_reason"].startswith("R5")


def test_账本只追加且每条自校验(tmp_path):
    ledger_path = tmp_path / "receipts.jsonl"
    log = DesktopReceiptLog(ledger_path)
    first = build_receipt(
        run_id="run-1", step=1, action="click", target=TARGET, before_digest=DIGEST_A
    )
    second = build_receipt(
        run_id="run-1", step=2, action="key",
        target={"window_id": "hwnd-1"}, before_digest=DIGEST_B,
    )

    log.append(first, {"before": "/tmp/1-before.png"})
    log.append(second)

    lines = [line for line in ledger_path.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 2
    record = json.loads(lines[0])
    assert record["kind"] == "desktop_action"
    assert record["digest"] == canonical_digest(record["payload"])
    assert record["shots"] == {"before": "/tmp/1-before.png"}

    reopened = DesktopReceiptLog(ledger_path)
    assert [item["payload"]["step"] for item in reopened.records()] == [1, 2]


def test_截图与观测不是同一帧时拒绝落盘(tmp_path):
    store = ShotStore(tmp_path / "shots")

    with pytest.raises(DesktopContractError):
        store.save("run-1", 1, "before", b"frame-x", expected_digest=DIGEST_A)


def test_receipt_payload_可被_json_序列化():
    receipt = build_receipt(
        run_id="run-1", step=1, action="type", target=TARGET, before_digest=DIGEST_A
    )

    assert json.loads(json.dumps(receipt_payload(receipt)))["action"] == "type"

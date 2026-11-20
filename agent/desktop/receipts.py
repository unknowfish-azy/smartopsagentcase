"""DH-06 证据接线：`UiActionReceipt` 构造、截图落盘、只追加账本。

三条纪律（对应 ARCHITECTURE §6「每步可证明」）：
1. **缺 after 就只能 UNVERIFIED**：没看见动作后的画面，不得声称成功；
2. **图片不进 receipt**：磁盘存 PNG，账本里只留 digest 与路径；
3. **只追加**：复用 recovery-contracts 的 JSONL 纪律，但写独立的
   `desktop_action` 记录，不改 `ReceiptLedger` 的 `receipt` / `event` schema，
   因此它读不回本该被忽略的行——桌面回执与恢复回执各走各的账本文件。

digest 算法只有一份：`agent.recovery_contracts.models.digest_of`。
`canonical_digest` 只是它的别名，供 ai-service 侧按同一规则交叉校验。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from agent.desktop.driver import shot_digest
from agent.desktop.models import DesktopContractError, UiActionReceipt, UiElement, UiObservation
from agent.recovery_contracts.models import digest_of

# 与 DS-01 共用同一个实现；不在此复制 canonical JSON 规则。
canonical_digest = digest_of

# 生产装配建议把账本放到与恢复回执同一个目录下（独立文件）：
#   DesktopReceiptLog(Path("agent/recovery_contracts/desktop_receipts.jsonl"))
DEFAULT_LEDGER_PATH = Path("agent/recovery_contracts/desktop_receipts.jsonl")

_SAFE_COMPONENT_RE = re.compile(r"[^A-Za-z0-9_-]+")
_PHASES = ("before", "after")


def element_diff(
    before: Iterable[UiElement],
    after: Iterable[UiElement],
) -> dict[str, list[str]]:
    """按 element_id 做集合差。

    `changed` 只可能是同一 id 的 `enabled` / `is_destructive` 翻转——
    id 本身由 (window, role, name, bbox) 哈希而来，几何或文案一改就是新 id，
    会落到 appeared / disappeared 里。
    """
    before_map = {element.element_id: element for element in before}
    after_map = {element.element_id: element for element in after}

    common = set(before_map) & set(after_map)
    changed = sorted(
        element_id
        for element_id in common
        if (before_map[element_id].enabled, before_map[element_id].is_destructive)
        != (after_map[element_id].enabled, after_map[element_id].is_destructive)
    )
    return {
        "appeared": sorted(set(after_map) - set(before_map)),
        "disappeared": sorted(set(before_map) - set(after_map)),
        "changed": changed,
    }


def build_receipt(
    *,
    run_id: str,
    step: int,
    action: str,
    target: Mapping[str, str],
    before_digest: str | None,
    after_digest: str | None = None,
    before_elements: Sequence[UiElement] = (),
    after_elements: Sequence[UiElement] = (),
    reject_reason: str | None = None,
) -> UiActionReceipt:
    """构造回执，verdict 由证据本身决定，不由调用方声称。

    * 有 reject_reason → REJECTED（after 一律不写）；
    * 没有 after 摘要 → UNVERIFIED（验收 ①）；
    * after 摘要与元素树都没有变化 → UNVERIFIED（画面没动，不算证明）；
    * 否则 → VERIFIED。
    """
    if reject_reason is not None:
        return UiActionReceipt(
            run_id=run_id,
            step=step,
            action=action,
            target=dict(target),
            before_shot_digest=before_digest,
            after_shot_digest=None,
            element_diff={},
            verdict="REJECTED",
            reject_reason=reject_reason,
        )

    if after_digest is None:
        return UiActionReceipt(
            run_id=run_id,
            step=step,
            action=action,
            target=dict(target),
            before_shot_digest=before_digest,
            after_shot_digest=None,
            element_diff={},
            verdict="UNVERIFIED",
        )

    diff = element_diff(before_elements, after_elements)
    changed = bool(any(diff.values())) or after_digest != before_digest
    return UiActionReceipt(
        run_id=run_id,
        step=step,
        action=action,
        target=dict(target),
        before_shot_digest=before_digest,
        after_shot_digest=after_digest,
        element_diff=diff,
        verdict="VERIFIED" if changed else "UNVERIFIED",
    )


def receipt_payload(receipt: UiActionReceipt) -> dict[str, Any]:
    """receipt → 可 JSON 序列化的字典（不含任何图片字节）。"""
    return {
        "run_id": receipt.run_id,
        "step": receipt.step,
        "action": receipt.action,
        "target": dict(receipt.target),
        "before_shot_digest": receipt.before_shot_digest,
        "after_shot_digest": receipt.after_shot_digest,
        "element_diff": {key: list(value) for key, value in receipt.element_diff.items()},
        "verdict": receipt.verdict,
        "reject_reason": receipt.reject_reason,
    }


class ShotStore:
    """截图落盘：`<root>/<run_id>/<step:04d>-{before|after}.png`。

    写入前校验文件 digest 与观测 digest 一致：图片和 receipt 必须指同一帧，
    否则"路径 + digest"这组证据就是假的。
    """

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def save(
        self,
        run_id: str,
        step: int,
        phase: str,
        png: bytes,
        *,
        expected_digest: str,
    ) -> str:
        if phase not in _PHASES:
            raise ValueError(f"phase 必须是 {_PHASES} 之一，收到: {phase!r}")
        if not run_id:
            raise ValueError("run_id 不能为空")

        digest = shot_digest(png)
        if digest != expected_digest:
            raise DesktopContractError(
                "截图 digest 与观测不一致：图片与元素树不是同一帧"
            )

        directory = self.root / _SAFE_COMPONENT_RE.sub("-", run_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{step:04d}-{phase}.png"
        path.write_bytes(png)
        return str(path)


class DesktopReceiptLog:
    """桌面动作回执的只追加账本（JSONL，一行一条）。

    `path=None` 时只保存在内存，供测试与"不落盘"场景；
    生产装配传入 `DEFAULT_LEDGER_PATH`。
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self._records: list[dict[str, Any]] = []
        if self.path is not None and self.path.exists():
            self._load()

    def _load(self) -> None:
        for line in Path(self.path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("kind") != "desktop_action":
                raise ValueError(f"未知审计记录类型：{record.get('kind')}")
            self._records.append(record)

    def append(
        self,
        receipt: UiActionReceipt,
        shots: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        payload = receipt_payload(receipt)
        record = {
            "kind": "desktop_action",
            "payload": payload,
            "shots": dict(shots or {}),
            # 记录自校验：改一行会被下游发现
            "digest": canonical_digest(payload),
        }
        self._records.append(record)

        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def records(self) -> list[dict[str, Any]]:
        return list(self._records)


def ensure_observation_pair(before: UiObservation, after: UiObservation) -> None:
    """同一次动作的前后观测必须来自同一个窗口，否则 diff 没有意义。"""
    if before.window_id != after.window_id:
        raise DesktopContractError(
            f"前后观测窗口不一致：{before.window_id} → {after.window_id}"
        )

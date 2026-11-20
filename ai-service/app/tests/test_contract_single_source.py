"""Z0-01：共享契约单一源守卫。

这批测试不实现任何能力，只防止"再来一份 canonical 实现"。

背景（实测）：
- `agent/recovery_contracts/models.py` 是 canonical JSON / digest 的唯一实现；
- `app/core/canonical.py` 只是转发（`canonical_digest = digest_of`）；
- `app/schemas/evidence_envelope.py` 直接引用 `object_digest`。

三条断言对应三个失败姿势：
1. 有人复制一份函数体（`is` 断言会红）；
2. 有人复制一份 digest 算法（AST 扫描会红）；
3. 有人让封套自己算 digest（`is` 断言会红）。
"""

from __future__ import annotations

import ast
from pathlib import Path

from agent.recovery_contracts import models as rc_models

from app.core.canonical import canonical_digest, digest_of
from app.schemas import evidence_envelope

APP_ROOT = Path(__file__).resolve().parents[1]  # ai-service/app
SKIP_DIRS = {"tests"}


def _dotted(node: ast.AST) -> str:
    """把 `hashlib.sha256` / `json.dumps` 这类属性访问还原成点号串。"""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _canonical_duplicates() -> list[str]:
    """找出同时出现 sha256 与 sort_keys json.dumps 的运行时模块。

    单独的 sha256（校验文件）或单独的 sort_keys（日志）都不算违规；
    两类同现才说明"有人在模块里重写了 canonical 摘要"。
    """
    duplicates: list[str] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        relative = path.relative_to(APP_ROOT)
        if relative.parts[0] in SKIP_DIRS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        has_sha256 = any(
            isinstance(node, ast.Call) and _dotted(node.func) == "hashlib.sha256"
            for node in ast.walk(tree)
        )
        has_canonical_dumps = any(
            isinstance(node, ast.Call)
            and _dotted(node.func) == "json.dumps"
            and any(
                keyword.arg == "sort_keys"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
                for keyword in node.keywords
            )
            for node in ast.walk(tree)
        )
        if has_sha256 and has_canonical_dumps:
            duplicates.append(str(path))
    return duplicates


def test_canonical_digest_forwards_to_recovery_contracts():
    """必须是同一个函数对象，不是同名副本。"""
    assert canonical_digest is rc_models.digest_of
    assert digest_of is rc_models.digest_of


def test_envelope_uses_same_object_digest():
    """封套不得自己实现 digest，必须引用同一份 object_digest。"""
    assert evidence_envelope.object_digest is rc_models.object_digest


def test_digest_agrees_across_modules():
    """跨模块同输入同输出：转发若被悄悄改写，这条会红。"""
    payload = {"b": 1, "a": [1, 2, {"z": None}], "中文": "值"}
    assert canonical_digest(payload) == rc_models.object_digest(payload)


def test_no_second_canonical_impl_in_runtime():
    """运行时目录里不允许出现第二份 canonical 摘要实现。"""
    duplicates = _canonical_duplicates()
    assert duplicates == [], (
        "检测到疑似重复的 canonical 摘要实现（同时使用 hashlib.sha256 与 "
        f"json.dumps(sort_keys=True)）：{duplicates}。"
        "请改为引用 agent.recovery_contracts.models.object_digest。"
    )

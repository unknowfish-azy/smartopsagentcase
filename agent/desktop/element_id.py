"""DH-01 稳定元素 id。

规则（ARCHITECTURE §5）：hash(window_id + role + name + bbox) 取前 16 hex。

稳定性要求：
- 同窗口同元素两次观测，id 相同；
- 元素消失后 id 不复用（bbox 参与哈希，位置变了就是另一个 id）。

本模块平台无关，不得 import 任何系统控制库。
"""

from __future__ import annotations

import hashlib
import re

ELEMENT_ID_RE = re.compile(r"^[a-f0-9]{16}$")

# 用不可见分隔符拼接，避免 "ab"+"c" 与 "a"+"bc" 撞成同一个输入。
_SEP = "\x1f"


def element_id(
    window_id: str,
    role: str,
    name: str,
    bbox: tuple[int, int, int, int],
) -> str:
    """返回 16 位十六进制的稳定元素 id。"""

    if not window_id:
        raise ValueError("window_id 不能为空")

    if not role:
        raise ValueError("role 不能为空")

    try:
        x0, y0, x1, y1 = (int(value) for value in bbox)
    except (TypeError, ValueError) as exc:
        raise ValueError("bbox 必须是 (x0, y0, x1, y1) 四个整数") from exc

    raw = _SEP.join(
        [
            str(window_id),
            str(role),
            str(name),
            f"{x0},{y0},{x1},{y1}",
        ]
    )

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

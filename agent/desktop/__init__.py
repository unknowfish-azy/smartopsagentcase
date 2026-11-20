"""桌面手（Desktop Hand）契约层与门禁层。

设计依据：docs/design/desktop-hand/ARCHITECTURE.md

分层铁律（§3）：
1. 只有 agent/desktop/driver.py 允许 import 系统控制库；
2. 只有 agent/desktop/gateway.py 允许做策略判断；
3. LLM 只产出 element_id，永不产出坐标；
4. 感知默认本地。

本包（契约 + 策略）必须平台无关，要能在阿里云 Linux 上导入。
"""

from agent.desktop.element_id import ELEMENT_ID_RE, element_id
from agent.desktop.gateway import (
    ALLOWED_KEYS,
    INPUT_ACTIONS,
    DesktopGateway,
    Decision,
)
from agent.desktop.models import (
    ACTIONS,
    NON_RISK_REJECT_REASONS,
    REJECT_REASONS,
    TARGET_KEYS,
    VERDICTS,
    DesktopContractError,
    UiActionReceipt,
    UiElement,
    UiObservation,
    WindowInfo,
    is_reject_reason,
)
from agent.desktop.policy import (
    DESTRUCTIVE_TEXT,
    FORBIDDEN_PROCESSES,
    FORBIDDEN_TITLE_KEYWORDS,
    DesktopPolicy,
    WindowRule,
    matches_destructive_text,
    normalize_process_name,
)

__all__ = [
    "ALLOWED_KEYS",
    "ACTIONS",
    "DESTRUCTIVE_TEXT",
    "DesktopContractError",
    "DesktopGateway",
    "DesktopPolicy",
    "Decision",
    "ELEMENT_ID_RE",
    "FORBIDDEN_PROCESSES",
    "FORBIDDEN_TITLE_KEYWORDS",
    "INPUT_ACTIONS",
    "NON_RISK_REJECT_REASONS",
    "REJECT_REASONS",
    "TARGET_KEYS",
    "UiActionReceipt",
    "UiElement",
    "UiObservation",
    "VERDICTS",
    "WindowInfo",
    "WindowRule",
    "element_id",
    "is_reject_reason",
    "matches_destructive_text",
    "normalize_process_name",
]

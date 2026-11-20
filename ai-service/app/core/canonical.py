"""DS-01 canonical JSON 摘要（最小实现，**与 DS-01 合并**）。

算法只有一份：直接转发 `agent.recovery_contracts.models` 的实现。
`app/schemas/evidence_envelope.py` 已经是同样的引用方式，这里只是给 DH-06
一个稳定的导入名 `canonical_digest`，不复制、不改写 canonical JSON 规则。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 生产部署和 pytest 都必须能 import agent —— 仓库根在 ai-service/ 之上 3 层。
_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from agent.recovery_contracts.models import (  # noqa: E402
    canonical_json,
    digest_of,
    object_digest,
)

canonical_digest = digest_of

__all__ = ["canonical_json", "canonical_digest", "digest_of", "object_digest"]

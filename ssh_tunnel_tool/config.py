"""JSON 配置持久化。密码只在运行时输入，不写入磁盘。"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from tunnel import TunnelConfig


class ConfigStore:
    def __init__(self, path: str | Path = "config.json") -> None:
        self.path = Path(path)

    def load(self) -> list[TunnelConfig]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [TunnelConfig(**item) for item in data]

    def save(self, configs: Iterable[TunnelConfig]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # 显式移除密码，避免凭据进入配置文件。
        payload = []
        for config in configs:
            item = asdict(config)
            item.pop("password", None)
            payload.append(item)
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

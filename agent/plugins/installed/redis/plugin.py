from __future__ import annotations

from pathlib import Path

from agent.sdk.manifest import PluginManifest
from agent.sdk.plugin import Plugin

from .tools import (
    RedisInfoTool,
    RedisMemoryTool,
    RedisRestartTool,
)


class RedisPlugin(Plugin):
    """
    SmartOps Redis Plugin。

    注册：

    - Permission
    - Risk Manifest
    - Tools
    """

    def __init__(self) -> None:

        manifest_path = (
            Path(__file__).parent
            / "manifest.yaml"
        )

        manifest = (
            PluginManifest.from_yaml(
                manifest_path
            )
        )

        super().__init__(
            manifest
        )

        self.tools = [
            RedisInfoTool(),
            RedisMemoryTool(),
            RedisRestartTool(),
        ]

    async def mount(
        self,
        runtime,
    ) -> None:

        # 1. 注册插件
        runtime.plugins.register(
            self
        )

        # 2. 注册Permission
        for permission in (
            self.manifest.permissions
        ):
            runtime.permissions.register(
                permission
            )

        # 3. 注册Risk Manifest
        if self.manifest.risk_manifest:

            runtime.risks.register(
                self.manifest.risk_manifest
            )

        # 4. 注册Tools
        for tool in self.tools:

            runtime.tools.register(
                tool
            )

    async def unmount(
        self,
        runtime,
    ) -> None:

        # 删除Tools
        for tool in self.tools:

            runtime.tools.unregister(
                tool.definition.name
            )

        # 删除插件
        runtime.plugins.unregister(
            self.id
        )
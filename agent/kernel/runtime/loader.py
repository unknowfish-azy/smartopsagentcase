from __future__ import annotations

import importlib


class InstalledPluginLoader:
    """
    自动发现并加载已安装Plugin。

    当前通过明确的Python模块导入，
    后续可以扩展为：
    - Plugin Marketplace
    - Git Provider
    - Entry Points
    - Plugin Manifest Discovery
    """

    DEFAULT_PLUGINS = {
        "docker": (
            "agent.plugins.installed.docker.plugin",
            "DockerPlugin",
        ),
        "kubernetes": (
            "agent.plugins.installed.kubernetes.plugin",
            "KubernetesPlugin",
        ),
        "mysql": (
            "agent.plugins.installed.mysql.plugin",
            "MySQLPlugin",
        ),
        "nginx": (
            "agent.plugins.installed.nginx.plugin",
            "NginxPlugin",
        ),
    }

    async def load_all(self, runtime) -> list[str]:

        loaded: list[str] = []

        for plugin_name, (
            module_name,
            class_name,
        ) in self.DEFAULT_PLUGINS.items():

            try:
                module = importlib.import_module(
                    module_name
                )

                plugin_class = getattr(
                    module,
                    class_name,
                )

                plugin = plugin_class()

                await runtime.mount_plugin(
                    plugin
                )

                loaded.append(plugin_name)

            except Exception:
                # 单个插件失败不应让整个Harness直接崩溃。
                continue

        return loaded
from abc import ABC

from agent.sdk.manifest import PluginManifest


class Plugin(ABC):
    """
    SmartOps插件基础类。

    插件负责：
    - 声明Manifest
    - mount时注册能力
    - unmount时释放能力
    """

    def __init__(
        self,
        manifest: PluginManifest,
    ) -> None:
        self.manifest = manifest

    @property
    def id(self) -> str:
        return self.manifest.plugin_id

    @property
    def version(self) -> str:
        return self.manifest.version

    async def mount(self, runtime) -> None:
        """
        插件安装/挂载阶段。
        """
        return None

    async def unmount(self, runtime) -> None:
        """
        插件卸载阶段。
        """
        return None
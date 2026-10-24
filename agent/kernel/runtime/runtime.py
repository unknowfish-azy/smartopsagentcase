from agent.kernel.event.bus import EventBus
from agent.kernel.event.events import (
    AgentEvent,
    PLUGIN_MOUNTED,
    PLUGIN_UNMOUNTED,
)
from agent.registry import (
    ModelRegistry,
    PermissionRegistry,
    PluginRegistry,
    ProviderRegistry,
    RiskRegistry,
    SkillRegistry,
    ToolRegistry,
)
from agent.kernel.lifecycle import (
    LifecycleManager,
    LifecycleState,
)


class AgentRuntime:

    def __init__(self) -> None:

        self.plugins = PluginRegistry()
        self.skills = SkillRegistry()
        self.tools = ToolRegistry()
        self.models = ModelRegistry()
        self.providers = ProviderRegistry()

        self.permissions = PermissionRegistry()
        self.risks = RiskRegistry()

        self.events = EventBus()
        self.lifecycle = LifecycleManager()

    async def mount_plugin(
        self,
        plugin,
    ) -> None:

        self.lifecycle.set_state(
            plugin.id,
            LifecycleState.MOUNTING,
        )

        try:

            await plugin.mount(self)

            self.lifecycle.set_state(
                plugin.id,
                LifecycleState.MOUNTED,
            )

            await self.events.publish(
                AgentEvent(
                    name=PLUGIN_MOUNTED,
                    payload={
                        "plugin_id": plugin.id,
                        "version": plugin.version,
                    },
                )
            )

        except Exception:

            self.lifecycle.set_state(
                plugin.id,
                LifecycleState.FAILED,
            )

            raise

    async def unmount_plugin(
        self,
        plugin,
    ) -> None:

        self.lifecycle.set_state(
            plugin.id,
            LifecycleState.UNMOUNTING,
        )

        await plugin.unmount(self)

        self.lifecycle.set_state(
            plugin.id,
            LifecycleState.STOPPED,
        )

        await self.events.publish(
            AgentEvent(
                name=PLUGIN_UNMOUNTED,
                payload={
                    "plugin_id": plugin.id
                },
            )
        )
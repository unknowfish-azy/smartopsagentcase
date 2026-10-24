from agent.registry.skill_registry import SkillRegistry
from agent.providers.skill.filesystem import (
    FilesystemSkillProvider,
)


class SkillProviderManager:

    def __init__(
        self,
        registry: SkillRegistry,
    ) -> None:

        self.registry = registry

    def load(
        self,
        provider: FilesystemSkillProvider,
    ) -> int:

        skills = provider.discover()

        for skill in skills:
            self.registry.register(skill)

        return len(skills)
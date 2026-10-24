from agent.sdk.skill import Skill


class SkillRegistry:

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill

    def unregister(self, name: str) -> None:
        self._skills.pop(name, None)

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def list(self) -> list[Skill]:
        return list(self._skills.values())

    def search(self, query: str) -> list[Skill]:
        return [
            skill
            for skill in self._skills.values()
            if skill.matches(query)
        ]
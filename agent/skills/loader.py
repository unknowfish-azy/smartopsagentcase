from pathlib import Path

from agent.sdk.skill import Skill


class PluginSkillLoader:

    def load_from_plugin(
        self,
        plugin_directory: str | Path,
    ) -> list[Skill]:

        root = (
            Path(plugin_directory)
            / "skills"
        )

        if not root.exists():
            return []

        skills: list[Skill] = []

        for file in root.glob("*.md"):

            content = file.read_text(
                encoding="utf-8"
            )

            name = file.stem

            description = (
                f"Installed plugin skill: {name}"
            )

            skills.append(
                Skill(
                    name=name,
                    description=description,
                    path=file.parent,
                    content=content,
                )
            )

        return skills
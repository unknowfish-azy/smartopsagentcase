import json
from pathlib import Path

from agent.sdk.skill import Skill


class FilesystemSkillProvider:

    def __init__(
        self,
        root: str | Path,
    ) -> None:

        self.root = Path(root).resolve()

    def discover(self) -> list[Skill]:

        if not self.root.exists():
            return []

        skills: list[Skill] = []

        for directory in self.root.iterdir():

            if not directory.is_dir():
                continue

            skill_file = (
                directory / "SKILL.md"
            )

            if not skill_file.exists():
                continue

            metadata_file = (
                directory
                / "metadata.json"
            )

            metadata = {}

            if metadata_file.exists():
                try:
                    metadata = json.loads(
                        metadata_file.read_text(
                            encoding="utf-8"
                        )
                    )
                except json.JSONDecodeError:
                    metadata = {}

            skills.append(
                Skill(
                    name=metadata.get(
                        "name",
                        directory.name,
                    ),
                    description=metadata.get(
                        "description",
                        "",
                    ),
                    version=metadata.get(
                        "version",
                        "1.0.0",
                    ),
                    path=directory,
                    tags=metadata.get(
                        "tags",
                        [],
                    ),
                )
            )

        return skills
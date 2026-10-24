"""
SmartOps Local Skill Loader.

负责从本地目录发现 Skill。

默认目录：

    agent/skills/local/
    agent/skills/installed/

Skill 最低要求：

    <skill-dir>/
        SKILL.md

可选：

    metadata.json
    README.md
    examples/
    references/
    scripts/

Loader 只负责：

    Discover
    Parse
    Load
    Register

Loader 不负责：

    Permission
    Risk
    Approval
    Execution
    Sandbox
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from agent.registry.skill_registry import SkillRegistry
from agent.sdk.skill import Skill


@dataclass(slots=True)
class DiscoveredSkill:
    """
    本地发现到的 Skill 信息。
    """

    name: str
    path: Path
    skill_file: Path
    metadata_file: Path | None = None

    @property
    def version(self) -> str:
        metadata = self.load_metadata()

        version = metadata.get("version")

        if isinstance(version, str) and version.strip():
            return version.strip()

        return "1.0.0"

    def load_metadata(self) -> dict:
        """
        读取 metadata.json。
        """
        if self.metadata_file is None:
            return {}

        try:
            content = self.metadata_file.read_text(
                encoding="utf-8"
            )

            data = json.loads(content)

            if isinstance(data, dict):
                return data

        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ):
            pass

        return {}

    def description(self) -> str:
        """
        获取 Skill 描述。
        """
        metadata = self.load_metadata()

        description = metadata.get("description")

        if isinstance(description, str):
            return description.strip()

        return ""


class LocalSkillLoader:
    """
    SmartOps 本地 Skill Loader。

    可以扫描：

        agent/skills/local
        agent/skills/installed
        自定义 Skill 目录

    然后将 Skill 注册进 SkillRegistry。
    """

    def __init__(
        self,
        registry: SkillRegistry,
        roots: Iterable[str | Path] | None = None,
        *,
        recursive: bool = True,
    ) -> None:
        self.registry = registry

        self.roots = [
            Path(root)
            for root in (
                roots or []
            )
        ]

        self.recursive = recursive

    # ------------------------------------------------------------------
    # Discover
    # ------------------------------------------------------------------

    def discover(self) -> list[DiscoveredSkill]:
        """
        扫描 Skill。
        """
        discovered: list[DiscoveredSkill] = []

        for root in self.roots:
            if not root.exists():
                continue

            if not root.is_dir():
                continue

            discovered.extend(
                self._discover_root(root)
            )

        return self._deduplicate(discovered)

    def _discover_root(
        self,
        root: Path,
    ) -> list[DiscoveredSkill]:
        """
        扫描单个目录。
        """
        results: list[DiscoveredSkill] = []

        if self.recursive:
            candidates = (
                path
                for path in root.rglob("*")
                if path.is_dir()
            )
        else:
            candidates = (
                path
                for path in root.iterdir()
                if path.is_dir()
            )

        for directory in candidates:
            skill_file = directory / "SKILL.md"

            if not skill_file.is_file():
                continue

            metadata_file = directory / "metadata.json"

            if not metadata_file.is_file():
                metadata_file = None

            name = directory.name

            results.append(
                DiscoveredSkill(
                    name=name,
                    path=directory,
                    skill_file=skill_file,
                    metadata_file=metadata_file,
                )
            )

        return results

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load(
        self,
        skill: DiscoveredSkill,
    ) -> Skill:
        """
        将一个发现到的 Skill 转成 SDK Skill。
        """
        metadata = skill.load_metadata()

        name = (
            metadata.get("name")
            or skill.name
        )

        description = (
            metadata.get("description")
            or ""
        )

        version = (
            metadata.get("version")
            or "1.0.0"
        )

        tags = metadata.get("tags")

        if not isinstance(tags, list):
            tags = []

        tags = [
            str(tag)
            for tag in tags
        ]

        content = skill.skill_file.read_text(
            encoding="utf-8"
        )

        return Skill(
            name=str(name),
            description=str(description),
            version=str(version),
            path=str(skill.path),
            tags=tags,
            content=content,
        )

    # ------------------------------------------------------------------
    # Register
    # ------------------------------------------------------------------

    def load_all(self) -> list[Skill]:
        """
        发现并注册全部 Skill。

        返回成功加载的 Skill。
        """
        loaded: list[Skill] = []

        for discovered in self.discover():
            try:
                skill = self.load(discovered)
                self._register(skill)
                loaded.append(skill)

            except Exception:
                # 单个 Skill 损坏时不能阻止其他 Skill 加载。
                continue

        return loaded

    def _register(
        self,
        skill: Skill,
    ) -> None:
        """
        注册 Skill。

        兼容现有 SkillRegistry 的 register API。
        """
        register = getattr(
            self.registry,
            "register",
            None,
        )

        if register is None:
            raise RuntimeError(
                "SkillRegistry 未提供 register()"
            )

        register(skill)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def _deduplicate(
        self,
        skills: list[DiscoveredSkill],
    ) -> list[DiscoveredSkill]:
        """
        根据 Skill name 去重。

        前面 roots 优先。
        """
        result: list[DiscoveredSkill] = []
        seen: set[str] = set()

        for skill in skills:
            key = skill.name.lower()

            if key in seen:
                continue

            seen.add(key)
            result.append(skill)

        return result

    def list_names(self) -> list[str]:
        """
        返回已经发现的 Skill 名称。
        """
        return [
            skill.name
            for skill in self.discover()
        ]

    def load_one(
        self,
        name: str,
    ) -> Skill | None:
        """
        按名称加载单个 Skill。
        """
        for discovered in self.discover():
            if discovered.name == name:
                skill = self.load(discovered)
                self._register(skill)
                return skill

        return None


def create_default_local_loader(
    registry: SkillRegistry,
    project_root: str | Path | None = None,
) -> LocalSkillLoader:
    """
    创建 SmartOps 默认 LocalSkillLoader。

    默认扫描：

        agent/skills/local
        agent/skills/installed

    如果传入 project_root：

        <project_root>/agent/skills/local
        <project_root>/agent/skills/installed
    """
    if project_root is None:
        current_file = Path(__file__).resolve()

        # agent/skills/local/loader.py
        # parent0 = local
        # parent1 = skills
        # parent2 = agent
        # parent3 = project root
        project_root = current_file.parents[3]

    root = Path(project_root)

    return LocalSkillLoader(
        registry=registry,
        roots=[
            root / "agent" / "skills" / "local",
            root / "agent" / "skills" / "installed",
        ],
        recursive=True,
    )


__all__ = [
    "DiscoveredSkill",
    "LocalSkillLoader",
    "create_default_local_loader",
]
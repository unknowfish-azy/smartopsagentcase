"""
SmartOps Git Skill Provider.

用于从Git仓库中发现和读取Skill。

支持场景：
- 本地Git仓库
- 已clone的远程Git仓库
- Git工作树
- 指定branch / tag / commit
- Skill目录发现
- SKILL.md读取
- metadata.json读取

安全原则：
1. Git Provider只负责获取Skill资源。
2. 不执行Skill中的脚本。
3. 不执行第三方安装脚本。
4. 不自动执行git hooks。
5. 不自动授予Permission。
6. 不自动跳过Risk / Policy / SafeAgent。
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.sdk.skill import Skill


@dataclass
class GitSkillSource:
    """
    Git Skill来源。

    repository可以是：
    - 本地路径
    - 已clone的Git仓库路径
    """

    repository: str | Path
    branch: str | None = None
    revision: str | None = None
    skills_path: str = "skills"

    def __post_init__(self) -> None:
        self.repository = Path(
            self.repository
        ).expanduser().resolve()


class GitSkillProvider:
    """
    Git Skill Provider。

    当前实现主要操作：
    - git rev-parse
    - git status
    - git ls-tree

    不自动执行：
    - git checkout
    - git pull
    - git merge
    - git reset
    """

    FRONT_MATTER_PATTERN = re.compile(
        r"^---\s*\n"
        r"(.*?)"
        r"\n---\s*\n",
        re.DOTALL,
    )

    def __init__(
        self,
        *,
        max_file_size: int = 1024 * 1024,
        command_timeout: int = 20,
    ) -> None:

        self.max_file_size = max_file_size
        self.command_timeout = command_timeout

    # ------------------------------------------------------------------
    # Git基础检查
    # ------------------------------------------------------------------

    def _validate_repository(
        self,
        source: GitSkillSource,
    ) -> Path:

        repository = Path(
            source.repository
        )

        if not repository.exists():
            raise FileNotFoundError(
                f"Git repository does not exist: "
                f"{repository}"
            )

        if not repository.is_dir():
            raise ValueError(
                f"Git repository path is not a directory: "
                f"{repository}"
            )

        git_dir = repository / ".git"

        if not git_dir.exists():
            raise ValueError(
                f"Not a Git repository: {repository}"
            )

        return repository

    def _run_git(
        self,
        repository: Path,
        *arguments: str,
    ) -> str:

        command = [
            "git",
            "-C",
            str(repository),
            *arguments,
        ]

        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.command_timeout,
            check=False,
        )

        if process.returncode != 0:
            raise RuntimeError(
                process.stderr.strip()
                or (
                    "Git command failed: "
                    + " ".join(arguments)
                )
            )

        return process.stdout

    # ------------------------------------------------------------------
    # Revision
    # ------------------------------------------------------------------

    def current_revision(
        self,
        source: GitSkillSource,
    ) -> str:

        repository = self._validate_repository(
            source
        )

        return self._run_git(
            repository,
            "rev-parse",
            "HEAD",
        ).strip()

    def current_branch(
        self,
        source: GitSkillSource,
    ) -> str:

        repository = self._validate_repository(
            source
        )

        return self._run_git(
            repository,
            "branch",
            "--show-current",
        ).strip()

    # ------------------------------------------------------------------
    # Git Tree
    # ------------------------------------------------------------------

    def list_files(
        self,
        source: GitSkillSource,
    ) -> list[str]:

        repository = self._validate_repository(
            source
        )

        revision = (
            source.revision
            or source.branch
            or "HEAD"
        )

        output = self._run_git(
            repository,
            "ls-tree",
            "-r",
            "--name-only",
            revision,
            "--",
            source.skills_path,
        )

        return [
            line.strip()
            for line in output.splitlines()
            if line.strip()
        ]

    # ------------------------------------------------------------------
    # File读取
    # ------------------------------------------------------------------

    def read_file(
        self,
        source: GitSkillSource,
        file_path: str,
    ) -> str:

        repository = self._validate_repository(
            source
        )

        relative = Path(
            file_path
        )

        if relative.is_absolute():
            raise ValueError(
                "Git skill file path must be relative"
            )

        if ".." in relative.parts:
            raise ValueError(
                "Path traversal is not allowed"
            )

        target = (
            repository
            / relative
        ).resolve()

        try:
            target.relative_to(
                repository
            )
        except ValueError as exc:
            raise ValueError(
                "Path escapes Git repository"
            ) from exc

        if not target.exists():
            raise FileNotFoundError(
                f"Skill file not found: {file_path}"
            )

        if not target.is_file():
            raise ValueError(
                f"Not a file: {file_path}"
            )

        file_size = target.stat().st_size

        if file_size > self.max_file_size:
            raise ValueError(
                f"Skill file exceeds maximum size: "
                f"{file_size} bytes"
            )

        return target.read_text(
            encoding="utf-8",
            errors="replace",
        )

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_front_matter(
        content: str,
    ) -> dict[str, Any]:

        match = (
            GitSkillProvider
            .FRONT_MATTER_PATTERN
            .match(content)
        )

        if not match:
            return {}

        raw = match.group(1)

        try:
            import yaml

            data = yaml.safe_load(raw)

            if isinstance(data, dict):
                return data

        except Exception:
            return {}

        return {}

    def _load_metadata(
        self,
        source: GitSkillSource,
        skill_directory: str,
    ) -> dict[str, Any]:

        metadata_file = (
            Path(skill_directory)
            / "metadata.json"
        )

        try:
            content = self.read_file(
                source,
                str(metadata_file),
            )
        except (
            FileNotFoundError,
            ValueError,
        ):
            return {}

        try:
            data = json.loads(content)

            if isinstance(data, dict):
                return data

        except json.JSONDecodeError:
            return {}

        return {}

    # ------------------------------------------------------------------
    # Build Skill
    # ------------------------------------------------------------------

    def _build_skill(
        self,
        *,
        source: GitSkillSource,
        skill_directory: str,
        content: str,
    ) -> Skill:

        front_matter = (
            self._parse_front_matter(
                content
            )
        )

        metadata = self._load_metadata(
            source,
            skill_directory,
        )

        merged = {
            **front_matter,
            **metadata,
        }

        skill_name = merged.get(
            "name",
            Path(
                skill_directory
            ).name,
        )

        description = merged.get(
            "description",
            "",
        )

        version = merged.get(
            "version",
            "1.0.0",
        )

        tags = merged.get(
            "tags",
            [],
        )

        if not isinstance(tags, list):
            tags = []

        revision = self.current_revision(
            source
        )

        skill = Skill(
            name=str(skill_name),
            description=str(description),
            version=str(version),
            path=(
                Path(source.repository)
                / skill_directory
            ),
            tags=[
                str(tag)
                for tag in tags
            ],
            content=content,
        )

        # 将Git来源信息作为Skill运行时元数据保留。
        # 当前Skill模型没有metadata字段，所以通过动态属性
        # 暂存，后续建议把source字段正式加入Skill模型。
        skill.source = {
            "type": "git",
            "repository": str(
                source.repository
            ),
            "branch": source.branch,
            "revision": revision,
            "path": skill_directory,
        }

        return skill

    # ------------------------------------------------------------------
    # Single Skill
    # ------------------------------------------------------------------

    def load_skill(
        self,
        source: GitSkillSource,
        skill_directory: str,
    ) -> Skill:

        skill_directory = skill_directory.strip(
            "/\\"
        )

        if not skill_directory:
            raise ValueError(
                "skill_directory is required"
            )

        skill_file = (
            Path(skill_directory)
            / "SKILL.md"
        )

        content = self.read_file(
            source,
            str(skill_file),
        )

        return self._build_skill(
            source=source,
            skill_directory=skill_directory,
            content=content,
        )

    # ------------------------------------------------------------------
    # Discover
    # ------------------------------------------------------------------

    def discover(
        self,
        source: GitSkillSource,
    ) -> list[Skill]:

        files = self.list_files(
            source
        )

        skill_directories: set[str] = set()

        for file_path in files:

            normalized = file_path.replace(
                "\\",
                "/",
            )

            if not normalized.endswith(
                "/SKILL.md"
            ):
                continue

            directory = normalized[
                :-len("/SKILL.md")
            ]

            if directory:
                skill_directories.add(
                    directory
                )

        skills: list[Skill] = []

        for directory in sorted(
            skill_directories
        ):

            try:
                skill = self.load_skill(
                    source,
                    directory,
                )

                skills.append(skill)

            except (
                OSError,
                ValueError,
                RuntimeError,
            ):
                continue

        return skills

    # ------------------------------------------------------------------
    # Local convenience
    # ------------------------------------------------------------------

    def discover_from_path(
        self,
        repository: str | Path,
        *,
        branch: str | None = None,
        revision: str | None = None,
        skills_path: str = "skills",
    ) -> list[Skill]:

        source = GitSkillSource(
            repository=repository,
            branch=branch,
            revision=revision,
            skills_path=skills_path,
        )

        return self.discover(
            source
        )

    def load_from_path(
        self,
        repository: str | Path,
        skill_directory: str,
        *,
        branch: str | None = None,
        revision: str | None = None,
        skills_path: str = "skills",
    ) -> Skill:

        source = GitSkillSource(
            repository=repository,
            branch=branch,
            revision=revision,
            skills_path=skills_path,
        )

        return self.load_skill(
            source,
            skill_directory,
        )
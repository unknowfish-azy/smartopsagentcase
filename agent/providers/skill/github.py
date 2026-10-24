"""
SmartOps GitHub Skill Provider.

用于从 GitHub 仓库获取 SmartOps Skill。

支持：
- GitHub repository URL
- GitHub raw URL
- 指定 branch / tag
- 发现 SKILL.md
- 读取 metadata.json
- 转换为统一 Skill 对象

安全原则：
1. 本Provider只负责获取Skill文件。
2. 不执行第三方Skill中的脚本。
3. 不自动安装Python/npm等依赖。
4. 不授予任何Tool权限。
5. Skill安装后仍必须经过：
   Manifest -> Permission -> Risk -> Policy -> SafeAgent
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from agent.sdk.skill import Skill


GITHUB_API = "https://api.github.com"


@dataclass
class GitHubSkillSource:
    """
    GitHub Skill来源信息。
    """

    owner: str
    repository: str
    branch: str = "main"
    path: str = ""

    @property
    def repo_url(self) -> str:
        return (
            f"https://github.com/"
            f"{self.owner}/"
            f"{self.repository}"
        )

    @property
    def api_contents_url(self) -> str:
        url = (
            f"{GITHUB_API}/repos/"
            f"{self.owner}/"
            f"{self.repository}/contents"
        )

        if self.path:
            url += f"/{self.path.strip('/')}"

        return url


class GitHubSkillProvider:
    """
    从GitHub仓库发现并加载Skill。

    推荐仓库结构：

    repository/
    ├── skills/
    │   ├── redis-performance/
    │   │   ├── SKILL.md
    │   │   └── metadata.json
    │   └── nginx-troubleshooting/
    │       ├── SKILL.md
    │       └── metadata.json
    └── README.md
    """

    def __init__(
        self,
        *,
        token: str | None = None,
        timeout: float = 20.0,
        user_agent: str = "SmartOpsAgent-SkillProvider/1.0",
    ) -> None:

        self.token = token
        self.timeout = timeout
        self.user_agent = user_agent

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": self.user_agent,
        }

        if self.token:
            headers["Authorization"] = (
                f"Bearer {self.token}"
            )

        return headers

    async def _request(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
        ) as client:

            response = await client.get(
                url,
                headers=self._headers(),
                params=params,
            )

            response.raise_for_status()

            return response.json()

    # ------------------------------------------------------------------
    # URL解析
    # ------------------------------------------------------------------

    def parse_repository_url(
        self,
        url: str,
    ) -> GitHubSkillSource:

        parsed = urlparse(url)

        if parsed.netloc.lower() not in {
            "github.com",
            "www.github.com",
        }:
            raise ValueError(
                "Only github.com repository URLs are supported"
            )

        parts = [
            item
            for item in parsed.path.split("/")
            if item
        ]

        if len(parts) < 2:
            raise ValueError(
                "Invalid GitHub repository URL"
            )

        owner = parts[0]
        repository = parts[1]

        if repository.endswith(".git"):
            repository = repository[:-4]

        branch = "main"
        path = ""

        # 支持：
        #
        # /owner/repo/tree/branch/path
        #
        if len(parts) >= 4 and parts[2] == "tree":
            branch = parts[3]

            if len(parts) > 4:
                path = "/".join(parts[4:])

        return GitHubSkillSource(
            owner=owner,
            repository=repository,
            branch=branch,
            path=path,
        )

    # ------------------------------------------------------------------
    # GitHub API
    # ------------------------------------------------------------------

    async def list_contents(
        self,
        source: GitHubSkillSource,
    ) -> list[dict[str, Any]]:

        params = {
            "ref": source.branch,
        }

        data = await self._request(
            source.api_contents_url,
            params=params,
        )

        if not isinstance(data, list):
            raise ValueError(
                "GitHub contents API did not return a directory"
            )

        return data

    async def get_file(
        self,
        source: GitHubSkillSource,
        file_path: str,
    ) -> str:

        url = (
            f"{GITHUB_API}/repos/"
            f"{source.owner}/"
            f"{source.repository}/contents/"
            f"{file_path.lstrip('/')}"
        )

        data = await self._request(
            url,
            params={
                "ref": source.branch,
            },
        )

        if data.get("type") != "file":
            raise ValueError(
                f"GitHub path is not a file: {file_path}"
            )

        content = data.get("content")

        if content is None:
            raise ValueError(
                f"GitHub file has no content: {file_path}"
            )

        encoded = re.sub(
            r"\s+",
            "",
            content,
        )

        try:
            decoded = base64.b64decode(
                encoded
            )
        except Exception as exc:
            raise ValueError(
                f"Failed to decode GitHub file: "
                f"{file_path}"
            ) from exc

        return decoded.decode(
            "utf-8",
            errors="replace",
        )

    # ------------------------------------------------------------------
    # Skill metadata
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_front_matter(
        content: str,
    ) -> dict[str, Any]:

        if not content.startswith("---"):
            return {}

        lines = content.splitlines()

        if len(lines) < 3:
            return {}

        try:
            end_index = lines[1:].index("---") + 1
        except ValueError:
            return {}

        front_matter = "\n".join(
            lines[
                1:end_index
            ]
        )

        try:
            import yaml

            data = yaml.safe_load(
                front_matter
            )

            if isinstance(data, dict):
                return data

        except Exception:
            return {}

        return {}

    @staticmethod
    def _build_skill(
        *,
        content: str,
        metadata: dict[str, Any],
        skill_directory: str,
    ) -> Skill:

        name = metadata.get(
            "name",
            Path(skill_directory).name,
        )

        description = metadata.get(
            "description",
            "",
        )

        version = metadata.get(
            "version",
            "1.0.0",
        )

        tags = metadata.get(
            "tags",
            [],
        )

        if not isinstance(tags, list):
            tags = []

        return Skill(
            name=str(name),
            description=str(description),
            version=str(version),
            path=Path(skill_directory),
            tags=[
                str(tag)
                for tag in tags
            ],
            content=content,
        )

    # ------------------------------------------------------------------
    # Single Skill
    # ------------------------------------------------------------------

    async def load_skill(
        self,
        source: GitHubSkillSource,
        skill_path: str,
    ) -> Skill:

        skill_directory = skill_path.strip("/")

        skill_file = (
            f"{skill_directory}/SKILL.md"
        )

        content = await self.get_file(
            source,
            skill_file,
        )

        metadata: dict[str, Any] = {}

        metadata_file = (
            f"{skill_directory}/metadata.json"
        )

        try:
            metadata_content = (
                await self.get_file(
                    source,
                    metadata_file,
                )
            )

            parsed_metadata = json.loads(
                metadata_content
            )

            if isinstance(
                parsed_metadata,
                dict,
            ):
                metadata = parsed_metadata

        except (
            httpx.HTTPStatusError,
            ValueError,
            json.JSONDecodeError,
        ):
            metadata = {}

        front_matter = (
            self._parse_front_matter(
                content
            )
        )

        merged_metadata = {
            **front_matter,
            **metadata,
        }

        return self._build_skill(
            content=content,
            metadata=merged_metadata,
            skill_directory=skill_directory,
        )

    # ------------------------------------------------------------------
    # Discover
    # ------------------------------------------------------------------

    async def discover(
        self,
        source: GitHubSkillSource,
    ) -> list[Skill]:

        contents = await self.list_contents(
            source
        )

        skills: list[Skill] = []

        for item in contents:

            item_type = item.get(
                "type"
            )

            item_name = item.get(
                "name"
            )

            item_path = item.get(
                "path"
            )

            if (
                item_type != "dir"
                or not item_name
                or not item_path
            ):
                continue

            try:
                children = await self.list_contents(
                    GitHubSkillSource(
                        owner=source.owner,
                        repository=source.repository,
                        branch=source.branch,
                        path=item_path,
                    )
                )
            except (
                httpx.HTTPError,
                ValueError,
            ):
                continue

            has_skill_file = any(
                child.get("type") == "file"
                and child.get("name") == "SKILL.md"
                for child in children
            )

            if not has_skill_file:
                continue

            try:
                skill = await self.load_skill(
                    source,
                    item_path,
                )
            except (
                httpx.HTTPError,
                ValueError,
            ):
                continue

            skills.append(skill)

        return skills

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    async def discover_from_url(
        self,
        repository_url: str,
    ) -> list[Skill]:

        source = self.parse_repository_url(
            repository_url
        )

        return await self.discover(
            source
        )

    async def load_from_url(
        self,
        repository_url: str,
        skill_path: str,
    ) -> Skill:

        source = self.parse_repository_url(
            repository_url
        )

        return await self.load_skill(
            source,
            skill_path,
        )
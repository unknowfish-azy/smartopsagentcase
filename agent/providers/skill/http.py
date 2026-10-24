"""
SmartOps HTTP Skill Provider.

用于通过HTTP/HTTPS获取Skill。

支持：
- 单个SKILL.md URL
- Skill目录URL
- metadata.json
- GitHub Raw URL
- GitLab Raw URL
- 普通HTTP服务器

安全原则：
1. 只支持HTTP/HTTPS。
2. 默认不执行远程内容。
3. 限制响应大小。
4. 限制重定向次数。
5. 不自动安装依赖。
6. 不自动执行脚本。
7. 不授予Tool权限。
8. 不绕过Permission / Risk / Policy。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from agent.sdk.skill import Skill


@dataclass
class HttpSkillSource:
    """
    HTTP Skill来源。
    """

    url: str

    def __post_init__(self) -> None:
        self.url = self.url.strip()

        parsed = urlparse(
            self.url
        )

        if parsed.scheme.lower() not in {
            "http",
            "https",
        }:
            raise ValueError(
                "Only HTTP and HTTPS are supported"
            )


class HttpSkillProvider:
    """
    HTTP Skill Provider。

    默认只允许读取内容。
    不执行任何远程脚本。
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
        timeout: float = 20.0,
        max_response_size: int = 1024 * 1024,
        max_redirects: int = 5,
        token: str | None = None,
        user_agent: str = (
            "SmartOpsAgent-HttpSkillProvider/1.0"
        ),
    ) -> None:

        self.timeout = timeout
        self.max_response_size = (
            max_response_size
        )
        self.max_redirects = (
            max_redirects
        )
        self.token = token
        self.user_agent = user_agent

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _headers(
        self,
    ) -> dict[str, str]:

        headers = {
            "Accept": (
                "text/markdown,"
                "application/json,"
                "text/plain,"
                "*/*"
            ),
            "User-Agent": self.user_agent,
        }

        if self.token:
            headers["Authorization"] = (
                f"Bearer {self.token}"
            )

        return headers

    async def _get(
        self,
        url: str,
    ) -> tuple[str, str]:

        source = HttpSkillSource(
            url
        )

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            max_redirects=self.max_redirects,
        ) as client:

            response = await client.get(
                source.url,
                headers=self._headers(),
            )

            response.raise_for_status()

            content_length = (
                response.headers.get(
                    "content-length"
                )
            )

            if content_length:

                try:
                    if (
                        int(content_length)
                        > self.max_response_size
                    ):
                        raise ValueError(
                            "HTTP response is too large"
                        )
                except ValueError as exc:

                    if str(exc) == (
                        "HTTP response is too large"
                    ):
                        raise

            content = response.content

            if len(content) > (
                self.max_response_size
            ):
                raise ValueError(
                    "HTTP response exceeds "
                    "maximum allowed size"
                )

            return (
                response.url.__str__(),
                content.decode(
                    "utf-8",
                    errors="replace",
                ),
            )

    # ------------------------------------------------------------------
    # URL utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _is_skill_file(
        url: str,
    ) -> bool:

        path = urlparse(url).path.lower()

        return path.endswith(
            "/skill.md"
        ) or path.endswith(
            "skill.md"
        )

    @staticmethod
    def _directory_url(
        url: str,
    ) -> str:

        if url.endswith("/"):
            return url

        parsed = urlparse(url)

        path = parsed.path

        if "/" not in path:
            return url + "/"

        return url.rsplit(
            "/",
            1,
        )[0] + "/"

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_front_matter(
        content: str,
    ) -> dict[str, Any]:

        match = (
            HttpSkillProvider
            .FRONT_MATTER_PATTERN
            .match(content)
        )

        if not match:
            return {}

        try:
            import yaml

            data = yaml.safe_load(
                match.group(1)
            )

            if isinstance(data, dict):
                return data

        except Exception:
            return {}

        return {}

    async def _get_metadata(
        self,
        base_url: str,
    ) -> dict[str, Any]:

        metadata_url = urljoin(
            base_url,
            "metadata.json",
        )

        try:
            _, content = await self._get(
                metadata_url
            )
        except (
            httpx.HTTPError,
            ValueError,
        ):
            return {}

        try:
            data = json.loads(
                content
            )

            if isinstance(
                data,
                dict,
            ):
                return data

        except json.JSONDecodeError:
            return {}

        return {}

    # ------------------------------------------------------------------
    # Build Skill
    # ------------------------------------------------------------------

    async def _build_skill(
        self,
        *,
        skill_url: str,
        content: str,
    ) -> Skill:

        base_url = self._directory_url(
            skill_url
        )

        front_matter = (
            self._parse_front_matter(
                content
            )
        )

        metadata = await self._get_metadata(
            base_url
        )

        merged = {
            **front_matter,
            **metadata,
        }

        parsed = urlparse(
            skill_url
        )

        filename = (
            parsed.path.rstrip("/")
            .split("/")[-1]
        )

        default_name = (
            filename
            if filename.lower()
            != "skill.md"
            else parsed.path
            .rstrip("/")
            .split("/")[-2]
            if len(
                parsed.path
                .rstrip("/")
                .split("/")
            ) >= 2
            else "remote-skill"
        )

        name = merged.get(
            "name",
            default_name,
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

        if not isinstance(
            tags,
            list,
        ):
            tags = []

        skill = Skill(
            name=str(name),
            description=str(description),
            version=str(version),
            path=None,
            tags=[
                str(tag)
                for tag in tags
            ],
            content=content,
        )

        skill.source = {
            "type": "http",
            "url": skill_url,
            "base_url": base_url,
        }

        return skill

    # ------------------------------------------------------------------
    # Single Skill
    # ------------------------------------------------------------------

    async def load_skill(
        self,
        url: str,
    ) -> Skill:

        source = HttpSkillSource(
            url
        )

        final_url, content = await self._get(
            source.url
        )

        # 如果提供的URL是目录，
        # 则自动寻找SKILL.md。
        if not self._is_skill_file(
            final_url
        ):

            base_url = self._directory_url(
                final_url
            )

            skill_url = urljoin(
                base_url,
                "SKILL.md",
            )

            final_url, content = (
                await self._get(
                    skill_url
                )
            )

        return await self._build_skill(
            skill_url=final_url,
            content=content,
        )

    # ------------------------------------------------------------------
    # Discover
    # ------------------------------------------------------------------

    async def discover(
        self,
        urls: list[str],
    ) -> list[Skill]:

        skills: list[Skill] = []

        for url in urls:

            try:
                skill = await self.load_skill(
                    url
                )

            except (
                httpx.HTTPError,
                ValueError,
            ):
                continue

            skills.append(
                skill
            )

        return skills

    async def discover_from_url(
        self,
        url: str,
    ) -> list[Skill]:

        return await self.discover(
            [url]
        )
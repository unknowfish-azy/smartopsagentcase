"""
Local Skill Loader Tests.
"""

from __future__ import annotations

from pathlib import Path

from agent.registry.skill_registry import SkillRegistry
from agent.skills.local.loader import LocalSkillLoader


def test_discover_installed_nginx_skill():
    """
    测试发现 nginx-troubleshooting。
    """
    project_root = (
        Path(__file__)
        .resolve()
        .parents[2]
    )

    skill_root = (
        project_root
        / "agent"
        / "skills"
        / "installed"
    )

    registry = SkillRegistry()

    loader = LocalSkillLoader(
        registry=registry,
        roots=[skill_root],
    )

    names = loader.list_names()

    assert (
        "nginx-troubleshooting"
        in names
    )


def test_load_installed_nginx_skill():
    """
    测试加载 nginx Skill。
    """
    project_root = (
        Path(__file__)
        .resolve()
        .parents[2]
    )

    skill_root = (
        project_root
        / "agent"
        / "skills"
        / "installed"
    )

    registry = SkillRegistry()

    loader = LocalSkillLoader(
        registry=registry,
        roots=[skill_root],
    )

    skill = loader.load_one(
        "nginx-troubleshooting"
    )

    assert skill is not None

    assert (
        skill.name
        == "nginx-troubleshooting"
    )

    assert (
        skill.version
    )

    assert (
        "Nginx"
        in skill.content
        or "nginx"
        in skill.content
    )


def test_no_duplicate_skill():
    """
    测试相同 Skill 不重复发现。
    """
    project_root = (
        Path(__file__)
        .resolve()
        .parents[2]
    )

    skill_root = (
        project_root
        / "agent"
        / "skills"
        / "installed"
    )

    registry = SkillRegistry()

    loader = LocalSkillLoader(
        registry=registry,
        roots=[
            skill_root,
            skill_root,
        ],
    )

    discovered = loader.discover()

    nginx_skills = [
        skill
        for skill in discovered
        if skill.name
        == "nginx-troubleshooting"
    ]

    assert len(
        nginx_skills
    ) == 1
"""
E2E SmartOps Agent Task Test.

完整预期链：

    User
      ↓
    Agent
      ↓
    Skill
      ↓
    Tool
      ↓
    Permission
      ↓
    Risk
      ↓
    Sandbox
      ↓
    Verification
      ↓
    Audit
"""

from __future__ import annotations

import os

import httpx
import pytest


@pytest.mark.e2e
def test_agent_task():
    """
    测试 Agent Task API。

    因为 Agent Runtime API 仍在演进，
    所以不在代码中硬编码最终接口。
    """
    agent_url = os.getenv(
        "SMARTOPS_AGENT_URL"
    )

    task_path = os.getenv(
        "SMARTOPS_AGENT_TASK_PATH",
        "/api/agent/tasks",
    )

    if not agent_url:
        pytest.skip(
            "未设置 SMARTOPS_AGENT_URL"
        )

    payload = {
        "task": (
            "检查 Nginx 当前是否运行，"
            "只执行只读诊断。"
        ),
        "dry_run": True,
    }

    with httpx.Client(
        timeout=30.0
    ) as client:
        response = client.post(
            (
                f"{agent_url.rstrip('/')}"
                f"{task_path}"
            ),
            json=payload,
        )

    assert response.status_code in {
        200,
        201,
        202,
    }

    data = response.json()

    assert isinstance(
        data,
        dict,
    )
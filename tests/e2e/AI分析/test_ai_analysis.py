"""
E2E AI Analysis Test.

链路：

    User Question
        ↓
    AI Service
        ↓
    RAG
        ↓
    Knowledge Service
        ↓
    Answer
"""

from __future__ import annotations

import pytest


@pytest.mark.e2e
def test_ai_analysis(
    http_client,
    require_ai_service,
):
    """
    测试 AI Service 基础对话链。
    """
    payload = {
        "message": (
            "Nginx 返回 502 Bad Gateway，"
            "应该如何排查？"
        )
    }

    response = http_client.post(
        f"{require_ai_service}/api/chat",
        json=payload,
    )

    assert response.status_code == 200

    data = response.json()

    assert isinstance(
        data,
        dict,
    )

    # 允许不同版本的 response schema。
    assert (
        "answer" in data
        or "message" in data
        or "data" in data
    )
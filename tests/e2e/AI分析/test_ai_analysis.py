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
import httpx


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
        # Real local-model generation is bounded separately from fast API reads.
        timeout=httpx.Timeout(120.0, connect=5.0),
    )

    assert response.status_code == 200

    data = response.json()

    assert isinstance(
        data,
        dict,
    )

    assert isinstance(data.get("answer"), str) and data["answer"].strip()
    assert isinstance(data.get("metadata"), dict)
    assert isinstance(data["metadata"].get("degraded"), bool)

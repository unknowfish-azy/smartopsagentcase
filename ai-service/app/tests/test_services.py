import pytest

from app.services.llm import LLMService
from app.services.rag import RAGService


@pytest.mark.asyncio
async def test_mock_llm():

    service = LLMService()

    result = await service.generate(
        "测试问题"
    )

    assert isinstance(
        result,
        str,
    )

    assert "测试问题" in result


def test_rag_context():

    context = RAGService.build_context(
        [
            {
                "content": "systemctl restart nginx",
                "source": "nginx.md",
                "version": "ubuntu-22.04",
            }
        ]
    )

    assert "nginx" in context

    assert "ubuntu-22.04" in context


def test_empty_rag_context():

    context = RAGService.build_context(
        []
    )

    assert "没有检索到" in context
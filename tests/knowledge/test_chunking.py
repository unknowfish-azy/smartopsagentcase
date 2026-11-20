import pytest

from knowledge.ingestion.chunker import TextChunker


def test_chunker_respects_size_and_overlap():
    chunks = TextChunker(chunk_size=10, chunk_overlap=2).split("doc", "0123456789abcdefghij")
    assert len(chunks) == 3
    assert chunks[0].content == "0123456789"
    assert chunks[1].content.startswith("89")


def test_chunk_overlap_must_be_smaller_than_size():
    with pytest.raises(ValueError):
        TextChunker(chunk_size=4, chunk_overlap=4)


def test_markdown_chunks_carry_title_and_section_context():
    text = (
        "# Docker 运维\n\n"
        "## 镜像加速\n\n"
        + ("配置 registry-mirrors 后重启 daemon。\n\n" * 30)
        + "## 日志排查\n\n"
        + "journalctl -u docker 查看守护进程日志。\n"
    )
    chunks = TextChunker(chunk_size=200, chunk_overlap=20).split(
        "doc", text, source="Docker运维课/x.md"
    )
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.content.startswith("【Docker 运维")
    assert any("日志排查" in chunk.content for chunk in chunks)
    # 标题层级会进入前缀，长小节被切开后仍带主题上下文
    assert any("镜像加速" in chunk.content.split("\n", 1)[0] for chunk in chunks)


def test_code_fence_heading_is_not_treated_as_section():
    text = "# 标题\n\n```python\n# 这不是标题\nprint(1)\n```\n\n正文内容。\n"
    chunks = TextChunker(chunk_size=200, chunk_overlap=20).split("doc", text)
    assert len(chunks) == 1
    assert "# 这不是标题" in chunks[0].content
    assert "这不是标题" not in chunks[0].content.split("\n", 1)[0]


def test_pdf_like_text_with_python_comments_keeps_clean_prefix():
    # PDF 转写稿：只有文档标题，正文里的 "# 注释" 是代码不是标题
    text = "# 尚硅谷-10-RAG\n\n" + ("\n".join(
        ["# 方法一：直接调用", "print(info)", "", "result = run(agent)", ""]
    ) * 20)
    chunks = TextChunker(chunk_size=200, chunk_overlap=20).split("doc", text)
    assert chunks
    for chunk in chunks:
        assert chunk.content.startswith("【尚硅谷-10-RAG】")
        assert len(chunk.content) <= 200


def test_long_prefix_does_not_degenerate_fixed_split():
    text = "# " + ("很长的标题" * 40) + "\n\n" + ("正文" * 300)
    chunks = TextChunker(chunk_size=100, chunk_overlap=60).split("doc", text)
    assert len(chunks) < 100
    assert all(len(chunk.content) <= 100 for chunk in chunks)


def test_plain_text_without_headings_has_no_prefix():
    chunks = TextChunker(chunk_size=10, chunk_overlap=2).split(
        "doc", "0123456789abcdefghij", source="catalog/INC-1"
    )
    assert chunks[0].content == "0123456789"

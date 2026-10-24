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

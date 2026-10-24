from knowledge.service import KnowledgeService


def test_document_ingestion_creates_chunks_and_metadata():
    service = KnowledgeService()
    count = service.add_document("nginx upstream timeout", source="nginx-guide", version="1.24")
    assert count == 1
    assert service.chunk_count == 1


def test_empty_document_is_not_ingested():
    assert KnowledgeService().add_document("   ") == 0

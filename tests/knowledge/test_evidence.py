from knowledge.service import KnowledgeService


def test_search_returns_evidence_and_citations():
    service = KnowledgeService()
    service.add_document("nginx upstream timeout", source="official-nginx", version="1.24")
    result = service.search("nginx timeout")
    assert result["evidences"]
    assert result["citations"]
    assert result["evidences"][0]["source"] == "official-nginx"

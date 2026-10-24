from knowledge.retrieval.models import RetrievalResult
from knowledge.retrieval.version_filter import VersionFilter


def test_version_filter_excludes_other_versions():
    results = [RetrievalResult("1", "old", 1.0, version="1.0"), RetrievalResult("2", "new", 1.0, version="2.0")]
    assert [item.chunk_id for item in VersionFilter.filter(results, "2.0")] == ["2"]

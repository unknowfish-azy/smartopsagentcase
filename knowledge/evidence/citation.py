from uuid import uuid4

from .models import Evidence

# 引用条目的摘要长度：够看清是哪段依据，又不至于把面板撑爆。
SNIPPET_LIMIT = 120


def _citation_title(evidence):

    source = (evidence.source or "").strip()

    if not source:
        return "参考资料"

    name = source.rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0] if "." in name else name

    return stem or name


def _citation_snippet(evidence):

    collapsed = " ".join((evidence.content or "").split()).lstrip("#").strip()

    if len(collapsed) <= SNIPPET_LIMIT:
        return collapsed

    return collapsed[:SNIPPET_LIMIT] + "…"


def build_evidence(results):

    evidences = []

    for result in results:

        evidences.append(
            Evidence(
                evidence_id=str(uuid4()),
                chunk_id=result.chunk_id,
                source=result.source,
                content=result.content,
                score=result.score,
                version=result.version,
                metadata=result.metadata,
            )
        )

    return evidences


def build_citations(evidences):

    citations = []

    for index, evidence in enumerate(
        evidences,
        start=1,
    ):
        citations.append(
            {
                "citation_id": index,
                "evidence_id": evidence.evidence_id,
                "title": _citation_title(evidence),
                "snippet": _citation_snippet(evidence),
                "source": evidence.source,
                "chunk_id": evidence.chunk_id,
                "version": evidence.version,
                "score": evidence.score,
            }
        )

    return citations
from uuid import uuid4

from .models import Evidence


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
                "source": evidence.source,
                "chunk_id": evidence.chunk_id,
                "version": evidence.version,
                "score": evidence.score,
            }
        )

    return citations
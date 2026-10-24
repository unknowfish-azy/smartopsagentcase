from datetime import datetime, timezone

from .models import DocumentChunk


def enrich_chunk(
    chunk: DocumentChunk,
    **metadata,
) -> DocumentChunk:

    chunk.metadata.update(metadata)

    chunk.metadata["ingested_at"] = (
        datetime.now(timezone.utc)
        .isoformat()
    )

    return chunk
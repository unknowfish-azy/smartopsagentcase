from uuid import uuid4

from .models import DocumentChunk


class TextChunker:

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 120,
    ):
        if chunk_overlap >= chunk_size:
            raise ValueError(
                "chunk_overlap 必须小于 chunk_size"
            )

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split(
        self,
        document_id: str,
        content: str,
        source: str = "",
        version: str = "latest",
    ) -> list[DocumentChunk]:

        content = content.strip()

        if not content:
            return []

        result = []

        start = 0
        index = 0

        while start < len(content):

            end = min(
                start + self.chunk_size,
                len(content),
            )

            chunk_text = content[start:end].strip()

            if chunk_text:
                result.append(
                    DocumentChunk(
                        chunk_id=str(uuid4()),
                        document_id=document_id,
                        content=chunk_text,
                        chunk_index=index,
                        source=source,
                        version=version,
                    )
                )

            if end >= len(content):
                break

            start = end - self.chunk_overlap
            index += 1

        return result
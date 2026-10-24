from dataclasses import dataclass, field
from typing import Dict


@dataclass
class DocumentChunk:
    chunk_id: str
    document_id: str

    content: str

    chunk_index: int

    title: str = ""

    source: str = ""

    version: str = "latest"

    metadata: Dict[str, str] = field(default_factory=dict)
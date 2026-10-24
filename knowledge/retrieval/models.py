from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class RetrievalResult:
    chunk_id: str
    content: str

    score: float

    source: str = ""
    document_id: str = ""
    version: str = "latest"

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )

    retrieval_type: str = ""
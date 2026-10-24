from dataclasses import dataclass, field


@dataclass
class Evidence:

    evidence_id: str

    chunk_id: str

    source: str

    content: str

    score: float

    version: str

    metadata: dict = field(
        default_factory=dict
    )
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class ParsedDocument:
    document_id: str
    filename: str
    content: str
    file_type: str
    metadata: Dict[str, str] = field(default_factory=dict)
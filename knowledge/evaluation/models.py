from dataclasses import dataclass


@dataclass
class EvaluationCase:

    question: str

    expected_chunk_ids: list[str]

    expected_answer: str = ""

    version: str = "latest"
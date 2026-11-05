import json

from .models import EvaluationCase


def load_dataset(
    file_path: str,
) -> list[EvaluationCase]:

    with open(
        file_path,
        "r",
        encoding="utf-8",
    ) as file:

        data = json.load(file)

    return [
        EvaluationCase(
            question=item["question"],
            expected_chunk_ids=item.get(
                "expected_chunk_ids",
                [],
            ),
            expected_sources=item.get(
                "expected_sources",
                [],
            ),
            expected_answer=item.get(
                "expected_answer",
                "",
            ),
            version=item.get(
                "version",
                "latest",
            ),
            style=item.get(
                "style",
                "verbatim",
            ),
        )
        for item in data
    ]

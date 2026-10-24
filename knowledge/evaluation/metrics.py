def hit_at_k(
    predicted_ids,
    expected_ids,
    k: int,
) -> float:

    predicted = set(
        predicted_ids[:k]
    )

    expected = set(expected_ids)

    return 1.0 if predicted & expected else 0.0


def recall_at_k(
    predicted_ids,
    expected_ids,
    k: int,
) -> float:

    expected = set(expected_ids)

    if not expected:
        return 0.0

    predicted = set(
        predicted_ids[:k]
    )

    return len(
        predicted & expected
    ) / len(expected)


def mrr(
    predicted_ids,
    expected_ids,
) -> float:

    expected = set(expected_ids)

    for index, item in enumerate(
        predicted_ids,
        start=1,
    ):
        if item in expected:
            return 1.0 / index

    return 0.0
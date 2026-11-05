import math


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


def ndcg_at_k(
    predicted_ids,
    expected_ids,
    k: int,
) -> float:
    """二值相关性 nDCG@k：命中记为 1，否则 0。"""
    expected = set(expected_ids)

    if not expected:
        return 0.0

    dcg = 0.0
    for index, item in enumerate(predicted_ids[:k], start=1):
        if item in expected:
            dcg += 1.0 / math.log2(index + 1)

    ideal = sum(
        1.0 / math.log2(index + 1)
        for index in range(1, min(len(expected), k) + 1)
    )

    if ideal == 0:
        return 0.0

    return dcg / ideal

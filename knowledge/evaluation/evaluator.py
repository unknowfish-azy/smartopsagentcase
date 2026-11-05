from .metrics import (
    hit_at_k,
    mrr,
    ndcg_at_k,
    recall_at_k,
)


def _match_expected(case) -> tuple[set[str], str]:
    """确定判定口径：优先 chunk_id（精确），否则退回 source（稳定）。"""
    if case.expected_chunk_ids:
        return set(case.expected_chunk_ids), "chunk"
    return set(case.expected_sources), "source"


class RetrievalEvaluator:

    def evaluate(
        self,
        cases,
        retriever,
        query_encoder,
        top_k: int = 5,
    ):

        hit_scores = []
        recall_scores = []
        mrr_scores = []
        ndcg_scores = []

        for case in cases:

            query_vector = query_encoder.encode(
                [case.question],
                is_query=True,
            )[0]

            results = retriever.search(
                query=case.question,
                query_vector=query_vector,
                top_k=top_k,
                version=case.version,
            )

            expected, match_by = _match_expected(case)

            predicted = [
                (
                    result.chunk_id
                    if match_by == "chunk"
                    else result.source
                )
                for result in results
            ]

            hit_scores.append(hit_at_k(predicted, expected, top_k))
            recall_scores.append(recall_at_k(predicted, expected, top_k))
            mrr_scores.append(mrr(predicted, expected))
            ndcg_scores.append(ndcg_at_k(predicted, expected, top_k))

        count = len(cases)

        if count == 0:
            return {
                "hit@k": 0.0,
                "recall@k": 0.0,
                "mrr": 0.0,
                "ndcg@k": 0.0,
            }

        return {
            "hit@k": sum(hit_scores) / count,
            "recall@k": sum(recall_scores) / count,
            "mrr": sum(mrr_scores) / count,
            "ndcg@k": sum(ndcg_scores) / count,
        }

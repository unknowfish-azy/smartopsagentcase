from .metrics import (
    hit_at_k,
    mrr,
    recall_at_k,
)


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

        for case in cases:

            query_vector = query_encoder.encode(
                [case.question]
            )[0]

            results = retriever.search(
                query=case.question,
                query_vector=query_vector,
                top_k=top_k,
                version=case.version,
            )

            predicted_ids = [
                result.chunk_id
                for result in results
            ]

            hit_scores.append(
                hit_at_k(
                    predicted_ids,
                    case.expected_chunk_ids,
                    top_k,
                )
            )

            recall_scores.append(
                recall_at_k(
                    predicted_ids,
                    case.expected_chunk_ids,
                    top_k,
                )
            )

            mrr_scores.append(
                mrr(
                    predicted_ids,
                    case.expected_chunk_ids,
                )
            )

        count = len(cases)

        if count == 0:
            return {
                "hit@k": 0.0,
                "recall@k": 0.0,
                "mrr": 0.0,
            }

        return {
            "hit@k": sum(hit_scores) / count,
            "recall@k": sum(recall_scores) / count,
            "mrr": sum(mrr_scores) / count,
        }
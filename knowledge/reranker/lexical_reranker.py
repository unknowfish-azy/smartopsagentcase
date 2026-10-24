import re


class LexicalReranker:

    @staticmethod
    def _tokens(text: str):
        return set(
            re.findall(
                r"[\u4e00-\u9fff]+|[a-zA-Z0-9_]+",
                text.lower(),
            )
        )

    def rerank(
        self,
        query: str,
        results,
        top_k: int = 5,
    ):

        query_tokens = self._tokens(query)

        reranked = []

        for result in results:

            content_tokens = self._tokens(
                result.content
            )

            overlap = (
                len(
                    query_tokens
                    & content_tokens
                )
                / max(
                    len(query_tokens),
                    1,
                )
            )

            final_score = (
                0.7 * result.score
                + 0.3 * overlap
            )

            result.score = final_score

            reranked.append(result)

        reranked.sort(
            key=lambda x: x.score,
            reverse=True,
        )

        return reranked[:top_k]
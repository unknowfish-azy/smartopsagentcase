from knowledge.retrieval.bm25 import tokenize


class LexicalReranker:

    @staticmethod
    def _tokens(text: str):
        # 与 BM25 共用同一套分词（中文 bigram），
        # 否则中文整段一个 token，重叠率恒为 0，重排对中文不起作用。
        return set(tokenize(text))

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

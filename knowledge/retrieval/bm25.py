import math
import re
from collections import Counter

from .models import RetrievalResult

_TOKEN_RUN = re.compile(r"[一-鿿]+|[a-z0-9_]+")
_CJK_RUN = re.compile(r"[一-鿿]+")


def tokenize(text: str) -> list[str]:
    """中英文混合分词。

    英文/数字/下划线按整词切；中文连续串切为二元组（bigram）。
    此前中文整段作为一个 token，导致 "抓不到指标怎么办" 这类口语 query
    在文档里几乎永远匹配不上，BM25 对中文检索实际上失效。
    bigram 不依赖外部词典，对同义改写和语序变化也更鲁棒。
    """
    tokens: list[str] = []
    for run in _TOKEN_RUN.findall(text.lower()):
        if _CJK_RUN.fullmatch(run):
            if len(run) == 1:
                tokens.append(run)
            else:
                tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
        else:
            tokens.append(run)
    return tokens


class BM25Retriever:

    def __init__(
        self,
        chunks=None,
        k1: float = 1.5,
        b: float = 0.75,
    ):
        self.chunks = chunks or []
        self.k1 = k1
        self.b = b

        self.documents = [
            tokenize(chunk.content)
            for chunk in self.chunks
        ]

        # 索引期一次性预计算：词频、文档频率、平均文档长度。
        # 此前每次查询都重算全库 df，并对每篇文档做 O(len) 的 count，
        # 语料上到几千 chunk 后单查询耗时随库容线性放大。
        self._term_freqs = [Counter(doc) for doc in self.documents]
        self._doc_lengths = [len(doc) for doc in self.documents]
        self._doc_count = len(self.documents)
        self._avg_len = (
            sum(self._doc_lengths) / self._doc_count
            if self._doc_count
            else 0.0
        )
        self._doc_freq: dict[str, int] = {}
        for term_freq in self._term_freqs:
            for token in term_freq:
                self._doc_freq[token] = self._doc_freq.get(token, 0) + 1
        # idf 只取决于 df 与文档总数，索引期算一次即可
        self._idf = {
            token: math.log(1 + (self._doc_count - df + 0.5) / (df + 0.5))
            for token, df in self._doc_freq.items()
        }

    def search(
        self,
        query: str,
        top_k: int = 10,
        version: str | None = None,  # 保留签名兼容，但不再自实现过滤
    ):
        """BM25 关键词检索。

        版本过滤：VERSION-P0-01 重构后由 KnowledgeService 层统一用 VersionFilter
        应用（任务书："召回前按服务端确认的 tenant/workspace/ACL 过滤；两路使用同一约束"）。
        本 retriever 只做 BM25 评分 + 排序 + top_k，不做版本过滤。

        version 参数保留以兼容现有调用方签名，但在此处不参与逻辑。
        """
        query_tokens = tokenize(query)

        if not query_tokens:
            return []

        document_count = self._doc_count

        if document_count == 0:
            return []

        avg_len = self._avg_len
        scores = [0.0] * document_count

        for index, term_freq in enumerate(self._term_freqs):
            score = 0.0
            doc_len = self._doc_lengths[index]

            for token in query_tokens:
                tf = term_freq.get(token, 0)

                if tf == 0:
                    continue

                idf = self._idf.get(token)
                if idf is None:
                    continue

                numerator = (
                    tf * (self.k1 + 1)
                )

                denominator = (
                    tf
                    + self.k1
                    * (
                        1
                        - self.b
                        + self.b
                        * doc_len
                        / max(avg_len, 1)
                    )
                )

                score += (
                    idf
                    * numerator
                    / denominator
                )

            scores[index] = score

        # 先算分再排序，只构造 top_k 个结果对象：
        # 此前每次查询都为全库 chunk 创建 RetrievalResult，库容越大越慢。
        order = sorted(
            range(document_count), key=scores.__getitem__, reverse=True
        )
        return [
            RetrievalResult(
                chunk_id=self.chunks[index].chunk_id,
                document_id=self.chunks[index].document_id,
                content=self.chunks[index].content,
                score=scores[index],
                source=self.chunks[index].source,
                version=self.chunks[index].version,
                metadata=self.chunks[index].metadata,
                retrieval_type="bm25",
            )
            for index in order[:top_k]
        ]

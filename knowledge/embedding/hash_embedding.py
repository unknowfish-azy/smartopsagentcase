import hashlib
import math
import re

# 与 BM25Retriever 使用同一套切分规则：连续中文串、连续字母数字串。
_TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]+|[a-zA-Z0-9_]+")


def tokenize_for_embedding(text: str) -> list[str]:
    """把文本切成可哈希的语义单元。

    中文没有空格，直接用 ``str.split()`` 会把整句当成一个 token，
    哈希后只落到一个维度上，向量检索等于随机。这里对中文补上
    单字 + 相邻二元组（bigram），使中文句子能落在多个维度上，
    与 BM25 的切分粒度保持一致。
    """
    tokens: list[str] = []
    for match in _TOKEN_PATTERN.finditer(text.lower()):
        piece = match.group()
        if "\u4e00" <= piece[0] <= "\u9fff":
            tokens.extend(piece)
            if len(piece) > 1:
                tokens.extend(piece[i:i + 2] for i in range(len(piece) - 1))
        else:
            tokens.append(piece)
    return tokens


class HashEmbedding:

    def __init__(self, dimension: int = 256):
        self._dimension = dimension

        # 同一语料里 token 重复率极高，缓存 token→维度映射，
        # 避免对每个 chunk 重复做 sha256。缓存到上限后整体清空即可。
        self._index_cache: dict[str, int] = {}

    def dimension(self) -> int:
        return self._dimension

    def _token_index(self, token: str) -> int:

        index = self._index_cache.get(token)

        if index is not None:
            return index

        digest = hashlib.sha256(
            token.encode("utf-8")
        ).digest()

        index = int.from_bytes(digest[:4], "big") % self._dimension

        if len(self._index_cache) >= 200_000:
            self._index_cache.clear()

        self._index_cache[token] = index

        return index

    def _encode_one(self, text: str) -> list[float]:

        vector = [0.0] * self._dimension

        for token in tokenize_for_embedding(text):
            vector[self._token_index(token)] += 1.0

        norm = math.sqrt(
            sum(x * x for x in vector)
        )

        if norm == 0:
            return vector

        return [
            x / norm
            for x in vector
        ]

    def encode(
        self,
        texts: list[str],
        *,
        is_query: bool = False,
    ) -> list[list[float]]:
        # 哈希词袋不区分 query/doc，参数仅为与 BgeEmbedding 接口保持一致。
        return [
            self._encode_one(text)
            for text in texts
        ]
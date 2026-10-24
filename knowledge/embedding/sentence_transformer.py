from .hash_embedding import HashEmbedding


class SentenceTransformerEmbedding:
    """
    基于 Sentence Transformers 的 Embedding 实现。

    外部模型服务调用已临时注释：sentence-transformers 需要在线下载
    预训练模型，缺少网络 / 密钥时会直接崩溃，因此默认回退到
    轻量级的 HashEmbedding 模拟向量。
    """

    def __init__(
        self,
        model_name: str,
    ):
        self.model_name = model_name

        # 【此处为外部模型服务调用，已临时注释，后续填入密钥即可恢复】
        # from sentence_transformers import SentenceTransformer
        # self.model = SentenceTransformer(model_name)

        # 模拟占位：使用 HashEmbedding 兜底，避免程序崩溃。
        self._fallback = HashEmbedding(dimension=384)

    def encode(
        self,
        texts: list[str],
    ) -> list[list[float]]:

        # 【此处为外部模型服务调用，已临时注释，后续填入密钥即可恢复】
        # vectors = self.model.encode(
        #     texts,
        #     normalize_embeddings=True,
        # )
        # return vectors.tolist()

        return self._fallback.encode(texts)

    def dimension(self) -> int:
        return self._fallback.dimension()

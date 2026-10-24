import hashlib
import math


class HashEmbedding:

    def __init__(self, dimension: int = 256):
        self._dimension = dimension

    def dimension(self) -> int:
        return self._dimension

    def _encode_one(self, text: str) -> list[float]:

        vector = [0.0] * self._dimension

        tokens = text.lower().split()

        for token in tokens:
            digest = hashlib.sha256(
                token.encode("utf-8")
            ).digest()

            index = int.from_bytes(
                digest[:4],
                "big",
            ) % self._dimension

            vector[index] += 1.0

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
    ) -> list[list[float]]:

        return [
            self._encode_one(text)
            for text in texts
        ]
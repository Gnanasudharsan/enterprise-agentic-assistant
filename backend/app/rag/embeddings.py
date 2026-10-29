"""Text embeddings: OpenAI-compatible API, or an offline hashing embedder."""

import hashlib
import math
import re
from collections.abc import Sequence
from typing import Protocol

import openai

from app.db.models import EMBEDDING_DIMENSIONS


class EmbeddingError(Exception):
    pass


class Embedder(Protocol):
    model: str

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def aclose(self) -> None: ...


class OpenAIEmbedder:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: float,
        max_retries: int,
        batch_size: int = 64,
    ) -> None:
        self.model = model
        self._batch_size = batch_size
        self._client = openai.AsyncOpenAI(
            api_key=api_key, base_url=base_url, timeout=timeout_seconds, max_retries=max_retries
        )

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = list(texts[start : start + self._batch_size])
            try:
                resp = await self._client.embeddings.create(
                    model=self.model, input=batch, dimensions=EMBEDDING_DIMENSIONS
                )
            except openai.APIError as exc:
                raise EmbeddingError(f"Embedding request failed: {type(exc).__name__}") from exc
            vectors.extend(item.embedding for item in sorted(resp.data, key=lambda d: d.index))
        return vectors

    async def aclose(self) -> None:
        await self._client.close()


_TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "did",
        "do",
        "does",
        "for",
        "from",
        "has",
        "have",
        "how",
        "i",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "our",
        "should",
        "that",
        "the",
        "their",
        "this",
        "to",
        "was",
        "we",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "you",
        "your",
    ]
)


class HashingEmbedder:
    """Deterministic, offline bag-of-words embedder (feature hashing of unigrams + bigrams).

    It captures lexical overlap only, not meaning. It exists so the full pipeline runs
    in CI and without an API key; evaluation reports always name the embedder used.
    """

    model = "hashing-v1"

    def _vector(self, text: str) -> list[float]:
        tokens = [t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS]
        features = tokens + [f"{a} {b}" for a, b in zip(tokens, tokens[1:], strict=False)]
        vec = [0.0] * EMBEDDING_DIMENSIONS
        for feature in features:
            digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % EMBEDDING_DIMENSIONS
            vec[index] += 1.0 if digest[4] & 1 else -1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if not norm:  # no content words; avoid a zero vector (undefined cosine distance)
            vec[0], norm = 1.0, 1.0
        return [v / norm for v in vec]

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    async def aclose(self) -> None:
        return None

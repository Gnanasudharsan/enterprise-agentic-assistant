"""Optional second-stage reranking of fused candidates."""

import json
import logging
import re
from collections.abc import Sequence
from typing import Protocol

from app.llm.base import ChatMessage, LLMClient, LLMError

logger = logging.getLogger(__name__)


class Reranker(Protocol):
    async def score(self, query: str, passages: Sequence[str]) -> list[float] | None:
        """Relevance score per passage (higher is better), or None to keep fused order."""
        ...


RERANK_PROMPT = """\
Rate how well each passage helps answer the question, from 0 (irrelevant) to 10 \
(directly answers it). Judge relevance only, not writing quality.

Question: {query}

{passages}

Respond with only JSON: {{"scores": [<one number per passage, in order>]}}"""


class LLMReranker:
    """Listwise relevance scoring with the chat model (one call per query).

    A cross-encoder is the classic choice here; an LLM judge needs no extra model
    download and is compared against no-rerank in the retrieval evaluation.
    """

    def __init__(self, llm: LLMClient, max_chars: int = 900) -> None:
        self._llm = llm
        self._max_chars = max_chars

    async def score(self, query: str, passages: Sequence[str]) -> list[float] | None:
        listing = "\n\n".join(
            f"[{i}] {p[: self._max_chars]}" for i, p in enumerate(passages, start=1)
        )
        prompt = RERANK_PROMPT.format(query=query, passages=listing)
        try:
            result = await self._llm.complete([ChatMessage(role="user", content=prompt)])
            match = re.search(r"\{.*\}", result.content, re.DOTALL)
            scores = json.loads(match.group(0))["scores"] if match else None
        except (LLMError, ValueError, KeyError, TypeError) as exc:
            logger.warning("Reranking failed, keeping fused order: %s", exc)
            return None
        if not isinstance(scores, list) or len(scores) != len(passages):
            logger.warning("Reranker returned %r scores for %d passages", scores, len(passages))
            return None
        try:
            return [float(s) for s in scores]
        except (TypeError, ValueError):
            return None

"""Hybrid retrieval: pgvector similarity + Postgres full-text search, fused with RRF.

Access control is applied inside both SQL queries (documents.acl must overlap the
caller's groups), so restricted passages never leave the database for that caller.
"""

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal

from sqlalchemy import String, cast, func, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document
from app.rag.embeddings import Embedder
from app.rag.reranking import Reranker

SearchMode = Literal["hybrid", "vector", "keyword"]

_QUERY_TERM = re.compile(r"[\w][\w-]*")


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    doc_key: str
    title: str
    section: str
    content: str
    source_path: str
    doc_type: str | None
    score: float
    vector_rank: int | None = None
    keyword_rank: int | None = None


def keyword_query(text: str) -> str:
    """OR together the query's terms for websearch_to_tsquery.

    Plain-language questions rarely contain *every* term of a passage, so AND
    semantics (the default) miss most matches; ranking still rewards overlap.
    Stopwords are dropped by Postgres; identifiers like INC-204 stay intact.
    """
    return " or ".join(_QUERY_TERM.findall(text))


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[uuid.UUID]], k: int
) -> dict[uuid.UUID, float]:
    scores: dict[uuid.UUID, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return scores


class Retriever:
    def __init__(
        self,
        embedder: Embedder,
        *,
        candidates: int = 20,
        top_k: int = 6,
        rrf_k: int = 60,
        reranker: Reranker | None = None,
    ) -> None:
        self.embedder = embedder
        self.candidates = candidates
        self.top_k = top_k
        self.rrf_k = rrf_k
        self.reranker = reranker

    def _visible(self, groups: Sequence[str]):
        return (
            select(Chunk.id)
            .join(Document, Document.id == Chunk.document_id)
            .where(Document.acl.overlap(cast(list(groups), ARRAY(String))))
        )

    async def _vector_ranking(
        self, session: AsyncSession, query: str, groups: Sequence[str]
    ) -> list[uuid.UUID]:
        [qvec] = await self.embedder.embed([query])
        stmt = (
            self._visible(groups)
            # Only compare vectors from the same embedding space as the query.
            .where(Document.embedding_model == self.embedder.model)
            .order_by(Chunk.embedding.cosine_distance(qvec))
            .limit(self.candidates)
        )
        return list((await session.scalars(stmt)).all())

    async def _keyword_ranking(
        self, session: AsyncSession, query: str, groups: Sequence[str]
    ) -> list[uuid.UUID]:
        terms = keyword_query(query)
        if not terms:
            return []
        tsquery = func.websearch_to_tsquery("english", terms)
        stmt = (
            self._visible(groups)
            .where(Chunk.search_vector.op("@@")(tsquery))
            .order_by(func.ts_rank(Chunk.search_vector, tsquery, 1).desc(), Chunk.id)
            .limit(self.candidates)
        )
        return list((await session.scalars(stmt)).all())

    async def search(
        self,
        session: AsyncSession,
        query: str,
        groups: Sequence[str],
        *,
        mode: SearchMode = "hybrid",
        top_k: int | None = None,
        rerank: bool = True,
    ) -> list[RetrievedChunk]:
        top_k = top_k or self.top_k
        vector = await self._vector_ranking(session, query, groups) if mode != "keyword" else []
        keyword = await self._keyword_ranking(session, query, groups) if mode != "vector" else []

        fused = reciprocal_rank_fusion([r for r in (vector, keyword) if r], self.rrf_k)
        use_reranker = rerank and self.reranker is not None
        # Give the reranker a wider pool than the final answer needs.
        pool = top_k * 2 if use_reranker else top_k
        ordered = sorted(fused, key=fused.__getitem__, reverse=True)[:pool]
        if not ordered:
            return []

        rows = await session.execute(
            select(Chunk, Document).join(Document).where(Chunk.id.in_(ordered))
        )
        by_id = {chunk.id: (chunk, doc) for chunk, doc in rows.all()}
        vector_rank = {cid: i for i, cid in enumerate(vector, start=1)}
        keyword_rank = {cid: i for i, cid in enumerate(keyword, start=1)}

        results = [
            RetrievedChunk(
                chunk_id=cid,
                doc_key=by_id[cid][1].doc_key,
                title=by_id[cid][1].title,
                section=by_id[cid][0].section,
                content=by_id[cid][0].content,
                source_path=by_id[cid][1].source_path,
                doc_type=by_id[cid][1].doc_type,
                score=fused[cid],
                vector_rank=vector_rank.get(cid),
                keyword_rank=keyword_rank.get(cid),
            )
            for cid in ordered
            if cid in by_id
        ]
        if use_reranker:
            assert self.reranker is not None
            scores = await self.reranker.score(query, [r.content for r in results])
            if scores is not None:
                results = [
                    replace(r, score=s)
                    for r, s in sorted(zip(results, scores, strict=True), key=lambda p: -p[1])
                ]
        return results[:top_k]

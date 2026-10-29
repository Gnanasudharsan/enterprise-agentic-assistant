"""Knowledge-base search (also used by the evaluation harness and for debugging)."""

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, get_retriever, get_user_groups
from app.rag.retrieval import Retriever
from app.schemas.search import SearchHit, SearchRequest, SearchResponse

router = APIRouter(prefix="/api/v1", tags=["knowledge base"])


@router.post("/search", response_model=SearchResponse)
async def search(
    body: SearchRequest,
    retriever: Annotated[Retriever, Depends(get_retriever)],
    groups: Annotated[list[str], Depends(get_user_groups)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> SearchResponse:
    hits = await retriever.search(
        db, body.query, groups, mode=body.mode, top_k=body.top_k, rerank=body.rerank
    )
    return SearchResponse(
        query=body.query,
        mode=body.mode,
        embedding_model=retriever.embedder.model,
        hits=[SearchHit(**asdict(h)) for h in hits],
    )

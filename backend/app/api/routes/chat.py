"""Grounded conversational question answering: JSON and streaming (SSE) variants.

Each request: (1) optionally retrieves passages from the knowledge base the caller may
read, (2) asks the model to answer from them with [S#] citations, (3) validates every
citation against the passages actually provided, and (4) records the run.
"""

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import __version__
from app.api.deps import (
    get_db_session,
    get_llm_client,
    get_retriever,
    get_settings_dep,
    get_user_groups,
)
from app.core.config import Settings
from app.db.models import ChatRun
from app.llm.base import ChatMessage, LLMClient, LLMError, LLMResult, LLMTimeoutError
from app.rag.embeddings import EmbeddingError
from app.rag.grounding import build_grounded_messages, check_citations, retrieval_query
from app.rag.retrieval import RetrievedChunk, Retriever
from app.schemas.chat import (
    MAX_HISTORY_MESSAGES,
    AssistantInfo,
    ChatRequest,
    ChatResponse,
    RetrievalStatus,
    Source,
    Usage,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["chat"])

SNIPPET_CHARS = 600


@dataclass(frozen=True)
class PreparedRequest:
    messages: list[ChatMessage]
    sources: list[RetrievedChunk]
    retrieval: RetrievalStatus


async def prepare(
    body: ChatRequest,
    settings: Settings,
    retriever: Retriever,
    groups: list[str],
    db: AsyncSession,
) -> PreparedRequest:
    history = [ChatMessage(role=m.role, content=m.content) for m in body.history]
    history = history[-MAX_HISTORY_MESSAGES:]
    plain = [
        ChatMessage(role="system", content=settings.llm_system_prompt),
        *history,
        ChatMessage(role="user", content=body.prompt),
    ]
    if not body.use_knowledge_base:
        return PreparedRequest(plain, [], "disabled")

    previous = next((m.content for m in reversed(history) if m.role == "user"), None)
    try:
        sources = await retriever.search(db, retrieval_query(body.prompt, previous), groups)
    except EmbeddingError as exc:
        # Degrade to an ungrounded answer rather than failing the whole request.
        logger.warning("Retrieval failed, answering without the knowledge base: %s", exc)
        return PreparedRequest(plain, [], "failed")

    messages = build_grounded_messages(settings.llm_system_prompt, history, body.prompt, sources)
    return PreparedRequest(messages, sources, "used" if sources else "no_results")


def elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def to_sources(chunks: list[RetrievedChunk]) -> list[Source]:
    return [
        Source(
            index=i,
            chunk_id=c.chunk_id,
            doc_key=c.doc_key,
            title=c.title,
            section=c.section,
            snippet=c.content[:SNIPPET_CHARS],
            source_path=c.source_path,
            doc_type=c.doc_type,
            score=round(c.score, 6),
        )
        for i, c in enumerate(chunks, start=1)
    ]


def failed_run(
    llm: LLMClient, prompt: str, prepared: PreparedRequest, exc: Exception, latency_ms: int
) -> ChatRun:
    return ChatRun(
        status="failed",
        provider=llm.provider,
        model=llm.model,
        prompt=prompt,
        error_type=type(exc).__name__,
        latency_ms=latency_ms,
        retrieved=retrieved_audit(prepared),
    )


def retrieved_audit(prepared: PreparedRequest) -> list[dict]:
    return [
        {"chunk_id": str(c.chunk_id), "doc_key": c.doc_key, "score": round(c.score, 6)}
        for c in prepared.sources
    ]


def finalize(
    llm: LLMClient, prompt: str, prepared: PreparedRequest, result: LLMResult, latency_ms: int
) -> tuple[ChatRun, ChatResponse]:
    check = check_citations(result.content, len(prepared.sources))
    if check.invalid:
        logger.warning("Removed %d invalid citation(s) from answer", check.invalid)
    run = ChatRun(
        id=uuid.uuid4(),  # assigned now: the response is built before the row is flushed
        status="succeeded",
        provider=llm.provider,
        model=result.model,
        prompt=prompt,
        answer=check.answer,
        latency_ms=latency_ms,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        retrieved=retrieved_audit(prepared),
        citations=[
            {"index": n, "chunk_id": str(prepared.sources[n - 1].chunk_id)} for n in check.cited
        ],
    )
    response = ChatResponse(
        run_id=run.id,
        answer=check.answer,
        provider=llm.provider,
        model=result.model,
        latency_ms=latency_ms,
        usage=Usage(prompt_tokens=result.prompt_tokens, completion_tokens=result.completion_tokens),
        retrieval=prepared.retrieval,
        sources=to_sources(prepared.sources),
        citations=check.cited,
        invalid_citations=check.invalid,
    )
    return run, response


def http_error_for(exc: LLMError) -> tuple[int, str]:
    if isinstance(exc, LLMTimeoutError):
        return status.HTTP_504_GATEWAY_TIMEOUT, "The language model timed out."
    return status.HTTP_502_BAD_GATEWAY, "The language model request failed."


@router.get("/info", response_model=AssistantInfo)
async def info(llm: Annotated[LLMClient, Depends(get_llm_client)]) -> AssistantInfo:
    """Which model is serving answers. `demo_mode` means no real model is connected."""
    return AssistantInfo(
        version=__version__,
        provider=llm.provider,
        model=llm.model,
        demo_mode=llm.provider == "fake",
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    llm: Annotated[LLMClient, Depends(get_llm_client)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    retriever: Annotated[Retriever, Depends(get_retriever)],
    groups: Annotated[list[str], Depends(get_user_groups)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChatResponse:
    started = time.perf_counter()
    prepared = await prepare(body, settings, retriever, groups, db)
    try:
        result = await llm.complete(prepared.messages)
    except LLMError as exc:
        # Failed runs are recorded too, so error rates are measurable later.
        db.add(failed_run(llm, body.prompt, prepared, exc, elapsed_ms(started)))
        await db.commit()
        logger.warning("LLM call failed: %s", exc)
        code, detail = http_error_for(exc)
        raise HTTPException(code, detail) from exc

    run, response = finalize(llm, body.prompt, prepared, result, elapsed_ms(started))
    db.add(run)
    await db.commit()
    return response


def sse(event: str, data: dict | list) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.post("/chat/stream")
async def chat_stream(
    body: ChatRequest,
    request: Request,
    llm: Annotated[LLMClient, Depends(get_llm_client)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    retriever: Annotated[Retriever, Depends(get_retriever)],
    groups: Annotated[list[str], Depends(get_user_groups)],
) -> StreamingResponse:
    """Server-Sent Events: one `sources` event, `delta` events with text, then `done` or
    `error`. The `done` payload carries the citation-checked final answer."""
    sessionmaker: async_sessionmaker = request.app.state.sessionmaker

    async def events() -> AsyncIterator[str]:
        started = time.perf_counter()
        async with sessionmaker() as db:
            prepared = await prepare(body, settings, retriever, groups, db)
        yield sse(
            "sources",
            {
                "retrieval": prepared.retrieval,
                "sources": [s.model_dump(mode="json") for s in to_sources(prepared.sources)],
            },
        )

        result: LLMResult | None = None
        try:
            async for item in llm.stream(prepared.messages):
                if isinstance(item, LLMResult):
                    result = item
                else:
                    yield sse("delta", {"text": item.text})
        except LLMError as exc:
            logger.warning("LLM stream failed: %s", exc)
            async with sessionmaker() as db:
                db.add(failed_run(llm, body.prompt, prepared, exc, elapsed_ms(started)))
                await db.commit()
            code, detail = http_error_for(exc)
            yield sse("error", {"status": code, "detail": detail})
            return

        if result is None:  # a client violating the stream() contract
            yield sse("error", {"status": 502, "detail": "The language model request failed."})
            return

        run, response = finalize(llm, body.prompt, prepared, result, elapsed_ms(started))
        async with sessionmaker() as db:
            db.add(run)
            await db.commit()
        yield sse("done", response.model_dump(mode="json"))

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        # Disable proxy buffering so tokens reach the browser immediately.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

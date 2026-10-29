"""Conversational question answering (Phase 1): JSON and streaming (SSE) variants."""

import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import __version__
from app.api.deps import get_db_session, get_llm_client, get_settings_dep
from app.core.config import Settings
from app.db.models import ChatRun
from app.llm.base import ChatMessage, LLMClient, LLMError, LLMResult, LLMTimeoutError
from app.schemas.chat import (
    MAX_HISTORY_MESSAGES,
    AssistantInfo,
    ChatRequest,
    ChatResponse,
    Usage,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["chat"])


def build_messages(body: ChatRequest, settings: Settings) -> list[ChatMessage]:
    history = body.history[-MAX_HISTORY_MESSAGES:]
    return [
        ChatMessage(role="system", content=settings.llm_system_prompt),
        *(ChatMessage(role=m.role, content=m.content) for m in history),
        ChatMessage(role="user", content=body.prompt),
    ]


def elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def failed_run(llm: LLMClient, prompt: str, exc: Exception, latency_ms: int) -> ChatRun:
    return ChatRun(
        status="failed",
        provider=llm.provider,
        model=llm.model,
        prompt=prompt,
        error_type=type(exc).__name__,
        latency_ms=latency_ms,
    )


def succeeded_run(llm: LLMClient, prompt: str, result: LLMResult, latency_ms: int) -> ChatRun:
    return ChatRun(
        status="succeeded",
        provider=llm.provider,
        model=result.model,
        prompt=prompt,
        answer=result.content,
        latency_ms=latency_ms,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
    )


def to_response(run: ChatRun) -> ChatResponse:
    return ChatResponse(
        run_id=run.id,
        answer=run.answer or "",
        provider=run.provider,
        model=run.model or "",
        latency_ms=run.latency_ms,
        usage=Usage(prompt_tokens=run.prompt_tokens, completion_tokens=run.completion_tokens),
    )


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
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChatResponse:
    started = time.perf_counter()
    try:
        result = await llm.complete(build_messages(body, settings))
    except LLMError as exc:
        # Failed runs are recorded too, so error rates are measurable later.
        db.add(failed_run(llm, body.prompt, exc, elapsed_ms(started)))
        await db.commit()
        logger.warning("LLM call failed: %s", exc)
        code, detail = http_error_for(exc)
        raise HTTPException(code, detail) from exc

    run = succeeded_run(llm, body.prompt, result, elapsed_ms(started))
    db.add(run)
    await db.commit()
    return to_response(run)


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.post("/chat/stream")
async def chat_stream(
    body: ChatRequest,
    request: Request,
    llm: Annotated[LLMClient, Depends(get_llm_client)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> StreamingResponse:
    """Server-Sent Events: `delta` events with text, then one `done` or `error` event."""
    sessionmaker: async_sessionmaker = request.app.state.sessionmaker
    messages = build_messages(body, settings)

    async def events() -> AsyncIterator[str]:
        started = time.perf_counter()
        result: LLMResult | None = None
        try:
            async for item in llm.stream(messages):
                if isinstance(item, LLMResult):
                    result = item
                else:
                    yield sse("delta", {"text": item.text})
        except LLMError as exc:
            logger.warning("LLM stream failed: %s", exc)
            async with sessionmaker() as db:
                db.add(failed_run(llm, body.prompt, exc, elapsed_ms(started)))
                await db.commit()
            code, detail = http_error_for(exc)
            yield sse("error", {"status": code, "detail": detail})
            return

        if result is None:  # a client violating the stream() contract
            yield sse("error", {"status": 502, "detail": "The language model request failed."})
            return

        run = succeeded_run(llm, body.prompt, result, elapsed_ms(started))
        async with sessionmaker() as db:
            db.add(run)
            await db.commit()
        yield sse("done", to_response(run).model_dump(mode="json"))

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        # Disable proxy buffering so tokens reach the browser immediately.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

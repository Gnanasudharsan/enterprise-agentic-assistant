"""Minimal single-turn question answering (Phase 1)."""

import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, get_llm_client, get_settings_dep
from app.core.config import Settings
from app.db.models import ChatRun
from app.llm.base import ChatMessage, LLMClient, LLMError, LLMTimeoutError
from app.schemas.chat import ChatRequest, ChatResponse, Usage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    llm: Annotated[LLMClient, Depends(get_llm_client)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> ChatResponse:
    messages = [
        ChatMessage(role="system", content=settings.llm_system_prompt),
        ChatMessage(role="user", content=body.prompt),
    ]

    started = time.perf_counter()
    try:
        result = await llm.complete(messages)
    except LLMError as exc:
        # Failed runs are recorded too, so error rates are measurable later.
        db.add(
            ChatRun(
                status="failed",
                provider=llm.provider,
                prompt=body.prompt,
                error_type=type(exc).__name__,
                latency_ms=round((time.perf_counter() - started) * 1000),
            )
        )
        await db.commit()
        logger.warning("LLM call failed: %s", exc)
        if isinstance(exc, LLMTimeoutError):
            raise HTTPException(
                status.HTTP_504_GATEWAY_TIMEOUT, "The language model timed out."
            ) from exc
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "The language model request failed."
        ) from exc
    latency_ms = round((time.perf_counter() - started) * 1000)

    run = ChatRun(
        status="succeeded",
        provider=llm.provider,
        model=result.model,
        prompt=body.prompt,
        answer=result.content,
        latency_ms=latency_ms,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
    )
    db.add(run)
    await db.commit()

    return ChatResponse(
        run_id=run.id,
        answer=result.content,
        provider=llm.provider,
        model=result.model,
        latency_ms=latency_ms,
        usage=Usage(
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
        ),
    )

"""Minimal single-turn question answering (Phase 1)."""

import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_llm_client, get_settings_dep
from app.core.config import Settings
from app.llm.base import ChatMessage, LLMClient, LLMError, LLMTimeoutError
from app.schemas.chat import ChatRequest, ChatResponse, Usage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    llm: Annotated[LLMClient, Depends(get_llm_client)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> ChatResponse:
    messages = [
        ChatMessage(role="system", content=settings.llm_system_prompt),
        ChatMessage(role="user", content=body.prompt),
    ]

    started = time.perf_counter()
    try:
        result = await llm.complete(messages)
    except LLMTimeoutError as exc:
        logger.warning("LLM timeout: %s", exc)
        raise HTTPException(
            status.HTTP_504_GATEWAY_TIMEOUT, "The language model timed out."
        ) from exc
    except LLMError as exc:
        logger.warning("LLM error: %s", exc)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "The language model request failed."
        ) from exc
    latency_ms = round((time.perf_counter() - started) * 1000)

    return ChatResponse(
        answer=result.content,
        provider=llm.provider,
        model=result.model,
        latency_ms=latency_ms,
        usage=Usage(
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
        ),
    )

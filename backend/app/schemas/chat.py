import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator

MAX_PROMPT_CHARS = 8000
MAX_HISTORY_MESSAGES = 20


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS * 2)


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    # Earlier turns of this conversation, oldest first. Only the most recent
    # MAX_HISTORY_MESSAGES are sent to the model, to bound cost and latency.
    history: list[HistoryMessage] = Field(default_factory=list, max_length=200)

    @field_validator("prompt")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("prompt must not be blank")
        return v


class Usage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class ChatResponse(BaseModel):
    run_id: uuid.UUID
    answer: str
    provider: str
    model: str
    latency_ms: int
    usage: Usage


class AssistantInfo(BaseModel):
    version: str
    provider: str
    model: str
    demo_mode: bool

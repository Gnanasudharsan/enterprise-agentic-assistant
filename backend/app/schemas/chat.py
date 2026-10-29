from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)

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
    answer: str
    provider: str
    model: str
    latency_ms: int
    usage: Usage

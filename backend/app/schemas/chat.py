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
    # Search the company knowledge base and ground the answer in what is found.
    use_knowledge_base: bool = True
    # Retrieval options, mainly for evaluation: which channels to search and whether to
    # rerank (None = the server's RERANKER setting).
    retrieval_mode: Literal["hybrid", "vector", "keyword"] = "hybrid"
    rerank: bool | None = None

    @field_validator("prompt")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("prompt must not be blank")
        return v


class Usage(BaseModel):
    """Tokens across every model call made for the request (reranking included)."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    llm_calls: int | None = None


class Source(BaseModel):
    """A retrieved passage shown to the model, numbered as cited in the answer ([S1]…)."""

    index: int
    chunk_id: uuid.UUID
    doc_key: str
    title: str
    section: str
    snippet: str
    source_path: str
    doc_type: str | None
    score: float


RetrievalStatus = Literal["used", "no_results", "disabled", "failed"]


class ChatResponse(BaseModel):
    run_id: uuid.UUID
    answer: str
    provider: str
    model: str
    latency_ms: int
    usage: Usage
    retrieval: RetrievalStatus = "disabled"
    sources: list[Source] = []
    # Source indices the answer cites, validated against `sources`, in order of first use.
    citations: list[int] = []
    # Citation markers the model produced that pointed to no provided source (removed).
    invalid_citations: int = 0


class AssistantInfo(BaseModel):
    version: str
    provider: str
    model: str
    demo_mode: bool
    # Today's token budget is spent, so answers come from the offline model until 00:00 UTC.
    budget_exhausted: bool = False
    embedding_model: str
    # The caller's access groups (what the knowledge base will show them).
    user_groups: list[str]

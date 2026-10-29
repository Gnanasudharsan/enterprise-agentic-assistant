import uuid
from typing import Literal

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    mode: Literal["hybrid", "vector", "keyword"] = "hybrid"
    top_k: int = Field(default=6, ge=1, le=20)
    rerank: bool = True


class SearchHit(BaseModel):
    chunk_id: uuid.UUID
    doc_key: str
    title: str
    section: str
    content: str
    source_path: str
    doc_type: str | None
    score: float
    vector_rank: int | None
    keyword_rank: int | None


class SearchResponse(BaseModel):
    query: str
    mode: str
    embedding_model: str
    hits: list[SearchHit]

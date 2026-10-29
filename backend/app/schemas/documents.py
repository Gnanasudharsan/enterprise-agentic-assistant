import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class DocumentSummary(BaseModel):
    id: uuid.UUID
    doc_key: str
    title: str
    doc_type: str | None
    owner: str | None
    version: str | None
    source_updated: str | None
    source_path: str
    acl: list[str]
    embedding_model: str
    chunk_count: int
    updated_at: datetime


class DocumentList(BaseModel):
    documents: list[DocumentSummary]


class UploadResult(BaseModel):
    status: Literal["created", "updated", "unchanged"]
    document: DocumentSummary


class ChunkDetail(BaseModel):
    chunk_id: uuid.UUID
    chunk_index: int
    section: str
    content: str
    token_count: int
    document: DocumentSummary

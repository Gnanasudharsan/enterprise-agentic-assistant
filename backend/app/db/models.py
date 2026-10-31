import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    BigInteger,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Fixed by the schema; text-embedding-3-small and the offline hashing embedder both use it.
EMBEDDING_DIMENSIONS = 1536


class ChatRun(Base):
    """One row per chat request: the start of the audit trail and LLMOps metrics."""

    __tablename__ = "chat_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    status: Mapped[str] = mapped_column(String(16))  # "succeeded" | "failed"
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(128))
    prompt: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    error_type: Mapped[str | None] = mapped_column(String(64))
    latency_ms: Mapped[int] = mapped_column(Integer)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    # Chunks shown to the model ([{chunk_id, score}]) and the citations it made that
    # were validated against them. Kept for auditing and offline evaluation.
    retrieved: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    citations: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)


class Document(Base):
    """A source document in the knowledge base (one row per logical document)."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    doc_key: Mapped[str] = mapped_column(String(128), unique=True)  # e.g. "INC-204"
    title: Mapped[str] = mapped_column(String(300))
    doc_type: Mapped[str | None] = mapped_column(String(32))
    owner: Mapped[str | None] = mapped_column(String(120))
    source_path: Mapped[str] = mapped_column(String(500))
    version: Mapped[str | None] = mapped_column(String(32))
    source_updated: Mapped[str | None] = mapped_column(String(32))
    # Groups allowed to read this document. Enforced in SQL on every retrieval.
    acl: Mapped[list[str]] = mapped_column(ARRAY(String(64)))
    content_hash: Mapped[str] = mapped_column(String(64))
    embedding_model: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (Index("ix_documents_acl", "acl", postgresql_using="gin"),)


class Chunk(Base):
    """A retrievable passage of a document, with keyword and vector representations."""

    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    section: Mapped[str] = mapped_column(String(500))  # heading path, e.g. "Handbook › PTO"
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('english', section), 'A') || "
            "setweight(to_tsvector('english', content), 'B')",
            persisted=True,
        ),
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))

    document: Mapped[Document] = relationship(back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index"),
        Index("ix_chunks_search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class AgentRun(Base):
    """One row per multi-agent run: the plan, the execution trace, and the outcome.

    The id doubles as the LangGraph thread id, so a run's checkpoints can be found (and an
    interrupted run resumed) from this row.
    """

    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    status: Mapped[str] = mapped_column(String(16))  # "running" | "succeeded" | "failed"
    question: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(128))
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # Ordered events: node, status, timing, and a summary of what each agent did.
    trace: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    answer: Mapped[str | None] = mapped_column(Text)
    sources: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    tables: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    # Validated citations: {"sources": [S#...], "tables": [T#...], "invalid": n}
    citations: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_type: Mapped[str | None] = mapped_column(String(64))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    # Every model call the run made (planner, repairs, analyst, drafts), summed over
    # resumptions.
    llm_calls: Mapped[int | None] = mapped_column(Integer)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)


class AgentAction(Base):
    """An action an agent proposed: the exact tool call, and what happened to it.

    `args_hash` fingerprints the arguments a human approved; the executor refuses to run
    if the stored arguments no longer match it.
    """

    __tablename__ = "agent_actions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    server: Mapped[str] = mapped_column(String(64))
    tool: Mapped[str] = mapped_column(String(64))
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON)
    args_hash: Mapped[str] = mapped_column(String(64))
    rationale: Mapped[str | None] = mapped_column(Text)
    # proposed -> approved -> executing -> executed | failed;  proposed -> rejected
    status: Mapped[str] = mapped_column(String(16), index=True)
    requested_by: Mapped[str] = mapped_column(String(64))
    decided_by: Mapped[str | None] = mapped_column(String(64))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)


class ActionAudit(Base):
    """Append-only log of every proposal, decision, denial, and execution."""

    __tablename__ = "action_audit"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    action_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_actions.id"), index=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    # proposed | edited | approved | rejected | denied | executing | executed | failed
    event: Mapped[str] = mapped_column(String(16))
    actor: Mapped[str] = mapped_column(String(64))  # a user id, or "agent" / "system"
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON)

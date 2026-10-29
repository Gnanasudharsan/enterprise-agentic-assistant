import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChatRun(Base):
    """One row per /chat request: the start of the audit trail and LLMOps metrics."""

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

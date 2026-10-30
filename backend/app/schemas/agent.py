import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.agents.plan import Plan
from app.schemas.chat import MAX_PROMPT_CHARS, HistoryMessage, Source


class AgentRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=200)

    @field_validator("prompt")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("prompt must not be blank")
        return v


class Chart(BaseModel):
    type: Literal["bar", "line"]
    x: str
    y: list[str]
    group: str | None = None  # split into one series per value of this column


class TableResult(BaseModel):
    """The result of one data step. `index` is the [T#] number, None if the step failed."""

    index: int | None
    step_id: str
    title: str
    question: str
    sql: str | None = None
    origin: Literal["generated", "certified"] | None = None
    columns: list[str] = []
    rows: list[list[Any]] = []
    row_count: int = 0
    truncated: bool = False
    elapsed_ms: int | None = None
    chart: Chart | None = None
    error: str | None = None
    # Failed attempts before the final query (each with the SQL and the error).
    attempts: list[dict[str, Any]] = []


class TraceEvent(BaseModel):
    node: str
    status: str
    started_at: str
    duration_ms: int
    summary: str
    detail: dict[str, Any] = {}


class AgentCitations(BaseModel):
    sources: list[int] = []
    tables: list[int] = []


RunStatus = Literal["running", "succeeded", "failed", "needs_approval"]

ActionStatus = Literal["proposed", "approved", "rejected", "executing", "executed", "failed"]


class ActionAuditEvent(BaseModel):
    event: str
    actor: str
    at: datetime | str | None
    detail: dict[str, Any] = {}


class ActionOut(BaseModel):
    """A tool call an agent proposed, its approval, and its outcome."""

    id: uuid.UUID
    run_id: uuid.UUID
    server: str
    tool: str
    arguments: dict[str, Any]
    rationale: str | None
    status: ActionStatus
    requested_by: str
    decided_by: str | None
    decided_at: datetime | None
    executed_at: datetime | None
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime | None
    audit: list[ActionAuditEvent] = []


class DecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]
    # Edited arguments to approve instead of the draft (validated against the tool schema).
    arguments: dict[str, Any] | None = None
    comment: str | None = Field(default=None, max_length=500)


class ToolOut(BaseModel):
    name: str
    server: str
    description: str
    input_schema: dict[str, Any]
    requires_approval: bool
    permitted: bool  # the caller's groups allow it


class AgentRunResponse(BaseModel):
    run_id: uuid.UUID
    status: RunStatus
    created_at: datetime | None = None
    question: str
    answer: str | None
    provider: str
    model: str | None
    latency_ms: int | None
    plan: Plan | None
    sources: list[Source] = []
    tables: list[TableResult] = []
    citations: AgentCitations = AgentCitations()
    invalid_citations: int = 0
    trace: list[TraceEvent] = []
    actions: list[ActionOut] = []
    error_type: str | None = None


class AgentRunSummary(BaseModel):
    run_id: uuid.UUID
    created_at: datetime
    status: RunStatus
    question: str
    latency_ms: int | None
    steps: int

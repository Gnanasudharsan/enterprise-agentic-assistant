"""Running the graph for API requests: streaming events, persistence, and resumption.

Every run gets an `agent_runs` row whose id is also the LangGraph thread id. The graph
checkpoints after each step, so a run that failed or was interrupted part-way (a provider
outage, a restart) can be resumed from its last completed step instead of starting over.
"""

import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from langgraph.graph.state import CompiledStateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agents.nodes import gather_evidence
from app.db.models import AgentRun
from app.llm.base import LLMClient, LLMError, LLMTimeoutError
from app.schemas.agent import AgentRunResponse, AgentRunSummary
from app.schemas.chat import MAX_HISTORY_MESSAGES, HistoryMessage

logger = logging.getLogger(__name__)

SNIPPET_CHARS = 600

Event = tuple[str, dict[str, Any]]


class RunNotFound(LookupError):
    pass


class RunNotResumable(RuntimeError):
    pass


def _source_out(s: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": s["index"],
        "chunk_id": s["chunk_id"],
        "doc_key": s["doc_key"],
        "title": s["title"],
        "section": s["section"],
        "snippet": s["content"][:SNIPPET_CHARS],
        "source_path": s["source_path"],
        "doc_type": s["doc_type"],
        "score": s["score"],
    }


def to_response(run: AgentRun) -> AgentRunResponse:
    citations = run.citations or {}
    return AgentRunResponse(
        run_id=run.id,
        status=run.status,
        created_at=run.created_at,
        question=run.question,
        answer=run.answer,
        provider=run.provider,
        model=run.model,
        latency_ms=run.latency_ms,
        plan=run.plan,
        sources=run.sources or [],
        tables=run.tables or [],
        citations={"sources": citations.get("sources", []), "tables": citations.get("tables", [])},
        invalid_citations=citations.get("invalid", 0),
        trace=run.trace or [],
        error_type=run.error_type,
    )


def error_detail(exc: Exception) -> tuple[int, str]:
    if isinstance(exc, LLMTimeoutError):
        return 504, "The language model timed out."
    if isinstance(exc, LLMError):
        return 502, "The language model request failed."
    return 500, "The agent run failed."


class AgentService:
    def __init__(
        self, graph: CompiledStateGraph, sessionmaker: async_sessionmaker, llm: LLMClient
    ) -> None:
        self.graph = graph
        self.sessionmaker = sessionmaker
        self.llm = llm

    @staticmethod
    def _config(run_id: uuid.UUID) -> dict:
        return {"configurable": {"thread_id": str(run_id)}}

    async def stream(
        self, question: str, history: list[HistoryMessage], groups: list[str]
    ) -> AsyncIterator[Event]:
        run = AgentRun(
            id=uuid.uuid4(),
            status="running",
            question=question,
            provider=self.llm.provider,
            model=self.llm.model,
        )
        async with self.sessionmaker() as db:
            db.add(run)
            await db.commit()
        yield "run", {"run_id": str(run.id), "resumed": False}
        inputs = {
            "run_id": str(run.id),
            "question": question,
            "history": [
                {"role": m.role, "content": m.content} for m in history[-MAX_HISTORY_MESSAGES:]
            ],
            "groups": list(groups),
        }
        async for event in self._execute(run.id, inputs):
            yield event

    async def resume(self, run_id: uuid.UUID) -> AsyncIterator[Event]:
        run = await self.get(run_id)
        if run.status == "succeeded":
            yield "done", run.model_dump(mode="json")
            return
        snapshot = await self.graph.aget_state(self._config(run_id))
        if not snapshot.values:
            raise RunNotResumable("No checkpoint exists for this run.")
        yield "run", {"run_id": str(run_id), "resumed": True, "pending": list(snapshot.next)}
        async for event in self._execute(run_id, None):  # None = continue from checkpoint
            yield event

    async def _execute(self, run_id: uuid.UUID, inputs: dict | None) -> AsyncIterator[Event]:
        started = time.perf_counter()
        config = self._config(run_id)
        try:
            async for chunk in self.graph.astream(inputs, config, stream_mode="custom"):
                payload = dict(chunk)
                yield payload.pop("type"), payload
        except Exception as exc:  # noqa: BLE001 - recorded on the run, then reported
            logger.exception("Agent run %s failed", run_id)
            values = (await self.graph.aget_state(config)).values
            await self._finish(run_id, values, started, error=exc)
            code, detail = error_detail(exc)
            yield "error", {"status": code, "detail": detail, "run_id": str(run_id),
                            "resumable": True}  # fmt: skip
            return
        values = (await self.graph.aget_state(config)).values
        response = await self._finish(run_id, values, started)
        yield "done", response.model_dump(mode="json")

    async def _finish(
        self,
        run_id: uuid.UUID,
        values: dict[str, Any],
        started: float,
        error: Exception | None = None,
    ) -> AgentRunResponse:
        sources, tables = gather_evidence(values) if values.get("plan") else ([], [])
        citations = values.get("citations", {})
        async with self.sessionmaker() as db:
            run = await db.get(AgentRun, run_id)
            assert run is not None
            run.status = "failed" if error else "succeeded"
            run.error_type = type(error).__name__ if error else None
            run.plan = values.get("plan")
            run.trace = values.get("trace", [])
            run.answer = None if error else values.get("answer")
            run.model = values.get("model") or run.model
            run.sources = [_source_out(s) for s in sources]
            run.tables = tables
            run.citations = {**citations, "invalid": values.get("invalid_citations", 0)}
            # Resumed runs accumulate the time of every attempt.
            run.latency_ms = (run.latency_ms or 0) + round((time.perf_counter() - started) * 1000)
            await db.commit()
            await db.refresh(run)
            return to_response(run)

    async def get(self, run_id: uuid.UUID) -> AgentRunResponse:
        async with self.sessionmaker() as db:
            run = await db.get(AgentRun, run_id)
        if run is None:
            raise RunNotFound(str(run_id))
        return to_response(run)

    async def list(self, limit: int = 20) -> list[AgentRunSummary]:
        async with self.sessionmaker() as db:
            runs = (
                await db.scalars(select(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit))
            ).all()
        return [
            AgentRunSummary(
                run_id=r.id,
                created_at=r.created_at,
                status=r.status,
                question=r.question,
                latency_ms=r.latency_ms,
                steps=len((r.plan or {}).get("steps", [])),
            )
            for r in runs
        ]

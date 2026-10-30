"""Running the graph for API requests: streaming events, persistence, and resumption.

Every run gets an `agent_runs` row whose id is also the LangGraph thread id. The graph
checkpoints after each step, so a run that failed or was interrupted part-way (a provider
outage, a restart) can be resumed from its last completed step instead of starting over.
"""

import logging
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.actions.gateway import ToolGateway
from app.actions.policy import ActionPolicy, PermissionDenied, args_hash
from app.actions.store import action_out, audit, audit_trail
from app.agents.action_nodes import validate_arguments
from app.agents.nodes import gather_evidence
from app.db.models import AgentAction, AgentRun
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


class ActionNotFound(LookupError):
    pass


class ActionConflict(RuntimeError):
    """The action is not waiting for a decision (already decided, or the run moved on)."""


class InvalidArguments(ValueError):
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


async def actions_for(db: AsyncSession, run_ids: list[uuid.UUID] | None = None,
                      status: str | None = None, limit: int = 50) -> list[dict]:  # fmt: skip
    stmt = select(AgentAction).order_by(AgentAction.created_at.desc()).limit(limit)
    if run_ids is not None:
        stmt = stmt.where(AgentAction.run_id.in_(run_ids))
    if status:
        stmt = stmt.where(AgentAction.status == status)
    rows = list((await db.scalars(stmt)).all())
    trails = await audit_trail(db, [r.id for r in rows])
    return [action_out(r, trails[r.id]) for r in rows]


def to_response(run: AgentRun, actions: list[dict] | None = None) -> AgentRunResponse:
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
        actions=actions or [],
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
        self,
        graph: CompiledStateGraph,
        sessionmaker: async_sessionmaker,
        llm: LLMClient,
        *,
        policy: ActionPolicy | None = None,
        tools: ToolGateway | None = None,
        user_id: str = "demo-user",
    ) -> None:
        self.graph = graph
        self.sessionmaker = sessionmaker
        self.llm = llm
        self.policy = policy or ActionPolicy({})
        self.tools = tools
        self.user_id = user_id

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
        if run.status == "needs_approval":
            raise RunNotResumable("This run is waiting for an approval decision.")
        snapshot = await self.graph.aget_state(self._config(run_id))
        if not snapshot.values:
            raise RunNotResumable("No checkpoint exists for this run.")
        yield "run", {"run_id": str(run_id), "resumed": True, "pending": list(snapshot.next)}
        async for event in self._execute(run_id, None):  # None = continue from checkpoint
            yield event

    async def _execute(
        self, run_id: uuid.UUID, inputs: dict | Command | None
    ) -> AsyncIterator[Event]:
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
        snapshot = await self.graph.aget_state(config)
        paused = "approval" in snapshot.next  # stopped at the interrupt, waiting for a human
        response = await self._finish(run_id, snapshot.values, started, paused=paused)
        if paused:
            pending = [a for a in response.actions if a.status == "proposed"]
            yield "approval_required", {"run_id": str(run_id),
                                        "action_ids": [str(a.id) for a in pending]}  # fmt: skip
        yield "done", response.model_dump(mode="json")

    async def _finish(
        self,
        run_id: uuid.UUID,
        values: dict[str, Any],
        started: float,
        error: Exception | None = None,
        paused: bool = False,
    ) -> AgentRunResponse:
        sources, tables = gather_evidence(values) if values.get("plan") else ([], [])
        citations = values.get("citations", {})
        async with self.sessionmaker() as db:
            run = await db.get(AgentRun, run_id)
            assert run is not None
            run.status = "failed" if error else "needs_approval" if paused else "succeeded"
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
            return to_response(run, await actions_for(db, [run_id]))

    async def get(self, run_id: uuid.UUID) -> AgentRunResponse:
        async with self.sessionmaker() as db:
            run = await db.get(AgentRun, run_id)
            if run is None:
                raise RunNotFound(str(run_id))
            return to_response(run, await actions_for(db, [run_id]))

    # ------------------------------------------------------------------ approvals

    async def record_decision(
        self,
        run_id: uuid.UUID,
        action_id: uuid.UUID,
        decision: str,
        groups: list[str],
        arguments: dict[str, Any] | None = None,
        comment: str | None = None,
    ) -> dict[str, Any]:
        """Validate and record a human decision. Returns the value the graph resumes with.

        Raises RunNotFound / ActionNotFound (404), PermissionDenied (403), ActionConflict
        (409), or InvalidArguments (422). Nothing is executed here.
        """
        async with self.sessionmaker() as db:
            run = await db.get(AgentRun, run_id)
            if run is None:
                raise RunNotFound(str(run_id))
            action = await db.get(AgentAction, action_id, with_for_update=True)
            if action is None or action.run_id != run_id:
                raise ActionNotFound(str(action_id))
            if action.status != "proposed" or run.status != "needs_approval":
                raise ActionConflict(f"This action is already {action.status}.")
            try:
                self.policy.check(action.tool, groups)
            except PermissionDenied as exc:
                audit(db, "denied", self.user_id, action_id=action.id, run_id=run_id,
                      reason=str(exc), attempted=decision)  # fmt: skip
                await db.commit()
                raise

            if decision == "approve":
                if arguments is not None and arguments != action.arguments:
                    spec = next((t for t in (self.tools.tools if self.tools else [])
                                 if t.name == action.tool), None)  # fmt: skip
                    if spec is None:
                        raise ActionConflict("The tool server is not connected.")
                    try:
                        validate_arguments(spec, arguments)
                    except ValueError as exc:
                        raise InvalidArguments(str(exc)) from exc
                    changed = sorted(k for k in {*arguments, *action.arguments}
                                     if arguments.get(k) != action.arguments.get(k))  # fmt: skip
                    audit(db, "edited", self.user_id, action_id=action.id, run_id=run_id,
                          fields=changed)  # fmt: skip
                    action.arguments = arguments
                action.args_hash = args_hash(action.tool, action.arguments)
                action.status = "approved"
            else:
                action.status = "rejected"
            action.decided_by = self.user_id
            action.decided_at = datetime.now(UTC)
            audit(db, action.status, self.user_id, action_id=action.id, run_id=run_id,
                  comment=comment)  # fmt: skip
            await db.commit()
            return {
                "decision": action.status,
                "by": self.user_id,
                "groups": list(groups),
                "args_hash": action.args_hash,
            }

    async def continue_after_decision(
        self, run_id: uuid.UUID, resume_value: dict[str, Any]
    ) -> AsyncIterator[Event]:
        yield "run", {"run_id": str(run_id), "resumed": True, "pending": ["execute_action"]}
        async for event in self._execute(run_id, Command(resume=resume_value)):
            yield event

    async def list_actions(self, status: str | None = None, limit: int = 50) -> list[dict]:
        async with self.sessionmaker() as db:
            return await actions_for(db, None, status, limit)

    async def get_action(self, action_id: uuid.UUID) -> dict:
        async with self.sessionmaker() as db:
            row = await db.get(AgentAction, action_id)
            if row is None:
                raise ActionNotFound(str(action_id))
            return action_out(row, (await audit_trail(db, [row.id]))[row.id])

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

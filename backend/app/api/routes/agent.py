"""Multi-agent research: the supervisor plans, specialists gather documents and data, and
the analyst writes a cited answer. Every run is recorded with its plan and full trace."""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.agents.service import AgentService, Event, RunNotFound, RunNotResumable
from app.api.deps import get_agent_service, get_user_groups
from app.api.routes.chat import sse
from app.schemas.agent import AgentRequest, AgentRunResponse, AgentRunSummary

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


def stream_response(events: AsyncIterator[Event]) -> StreamingResponse:
    async def body() -> AsyncIterator[str]:
        async for name, data in events:
            yield sse(name, data)

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/stream")
async def agent_stream(
    body: AgentRequest,
    service: Annotated[AgentService, Depends(get_agent_service)],
    groups: Annotated[list[str], Depends(get_user_groups)],
) -> StreamingResponse:
    """Server-Sent Events, in order: `run` (the run id), `step` and `plan` (supervisor),
    `step` / `sql` (specialists, interleaved while they run in parallel), `evidence`
    (numbered sources and tables), `answer_reset` + `delta` (the answer), then `done`
    (the full run, as GET /runs/{id} returns it) or `error`."""
    return stream_response(service.stream(body.prompt, body.history, groups))


@router.post("/run", response_model=AgentRunResponse)
async def agent_run(
    body: AgentRequest,
    service: Annotated[AgentService, Depends(get_agent_service)],
    groups: Annotated[list[str], Depends(get_user_groups)],
) -> AgentRunResponse:
    async for name, data in service.stream(body.prompt, body.history, groups):
        if name == "done":
            return AgentRunResponse.model_validate(data)
        if name == "error":
            raise HTTPException(
                data["status"], {"detail": data["detail"], "run_id": data["run_id"]}
            )
    raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "The agent run did not finish.")


@router.get("/runs", response_model=list[AgentRunSummary])
async def list_runs(
    service: Annotated[AgentService, Depends(get_agent_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[AgentRunSummary]:
    return await service.list(limit)


@router.get("/runs/{run_id}", response_model=AgentRunResponse)
async def get_run(
    run_id: uuid.UUID, service: Annotated[AgentService, Depends(get_agent_service)]
) -> AgentRunResponse:
    """A run's plan, execution trace (every agent step with timing and outcome), the SQL
    that was run, the evidence, and the answer."""
    try:
        return await service.get(run_id)
    except RunNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found.") from exc


@router.post("/runs/{run_id}/resume")
async def resume_run(
    run_id: uuid.UUID, service: Annotated[AgentService, Depends(get_agent_service)]
) -> StreamingResponse:
    """Continue a failed or interrupted run from its last checkpoint (same SSE events).
    Steps that already completed are not repeated."""
    try:
        await service.get(run_id)
    except RunNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found.") from exc
    events = service.resume(run_id)
    try:
        first = await anext(events)
    except RunNotResumable as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    async def chained() -> AsyncIterator[Event]:
        yield first
        async for event in events:
            yield event

    return stream_response(chained())

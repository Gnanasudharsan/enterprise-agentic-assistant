"""Multi-agent research: the supervisor plans, specialists gather documents and data, and
the analyst writes a cited answer. Every run is recorded with its plan and full trace."""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.actions.policy import PermissionDenied
from app.agents.service import (
    ActionConflict,
    ActionNotFound,
    AgentService,
    Event,
    InvalidArguments,
    RunNotFound,
    RunNotResumable,
)
from app.api.deps import get_agent_service, get_user_groups
from app.api.routes.chat import sse
from app.schemas.agent import (
    ActionOut,
    AgentRequest,
    AgentRunResponse,
    AgentRunSummary,
    DecisionRequest,
    ToolOut,
)

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])
actions_router = APIRouter(prefix="/api/v1", tags=["actions"])


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
    (numbered sources and tables), `answer_reset` + `delta` (the answer), `action` (a
    drafted tool call) + `approval_required` when the plan includes an action, then `done`
    (the full run, as GET /runs/{id} returns it; status `needs_approval` while paused) or
    `error`."""
    return stream_response(service.stream(body.prompt, body.history, groups))


@router.post("/run", response_model=AgentRunResponse)
async def agent_run(
    body: AgentRequest,
    service: Annotated[AgentService, Depends(get_agent_service)],
    groups: Annotated[list[str], Depends(get_user_groups)],
) -> AgentRunResponse:
    async for name, data in service.stream(body.prompt, body.history, groups):
        if name == "done":  # also returned while waiting for approval (status needs_approval)
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


@router.post("/runs/{run_id}/actions/{action_id}/decision")
async def decide_action(
    run_id: uuid.UUID,
    action_id: uuid.UUID,
    body: DecisionRequest,
    service: Annotated[AgentService, Depends(get_agent_service)],
    groups: Annotated[list[str], Depends(get_user_groups)],
) -> StreamingResponse:
    """Approve (optionally with edited arguments) or reject a proposed action, then resume
    the paused run (SSE: `action` updates, then `done`). The backend checks the caller's
    permission here and again right before executing; the model has no say in either."""
    try:
        resume_value = await service.record_decision(
            run_id, action_id, body.decision, groups, body.arguments, body.comment
        )
    except (RunNotFound, ActionNotFound) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Action not found.") from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except ActionConflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except InvalidArguments as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return stream_response(service.continue_after_decision(run_id, resume_value))


@actions_router.get("/tools", response_model=list[ToolOut])
async def list_tools(
    service: Annotated[AgentService, Depends(get_agent_service)],
    groups: Annotated[list[str], Depends(get_user_groups)],
) -> list[ToolOut]:
    """Tools reachable through MCP, with the backend's policy for the caller."""
    if service.tools is None:
        return []
    return [
        ToolOut(
            name=t.name,
            server=service.tools.server,
            description=t.description,
            input_schema=t.input_schema,
            requires_approval=service.policy.requires_approval(t.name),
            permitted=service.policy.can_use(t.name, groups),
        )
        for t in service.tools.tools
    ]


@actions_router.get("/actions", response_model=list[ActionOut])
async def list_actions(
    service: Annotated[AgentService, Depends(get_agent_service)],
    status_: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ActionOut]:
    """Proposed, approved, rejected, and executed actions, each with its audit trail."""
    return [ActionOut.model_validate(a) for a in await service.list_actions(status_, limit)]


@actions_router.get("/actions/{action_id}", response_model=ActionOut)
async def get_action(
    action_id: uuid.UUID, service: Annotated[AgentService, Depends(get_agent_service)]
) -> ActionOut:
    try:
        return ActionOut.model_validate(await service.get_action(action_id))
    except ActionNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Action not found.") from exc

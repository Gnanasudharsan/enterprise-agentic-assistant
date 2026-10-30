"""Persistence helpers for actions and their audit trail."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ActionAudit, AgentAction


def audit(
    db: AsyncSession,
    event: str,
    actor: str,
    *,
    action_id: uuid.UUID | None = None,
    run_id: uuid.UUID | None = None,
    **detail: Any,
) -> None:
    db.add(
        ActionAudit(
            action_id=action_id, run_id=run_id, event=event, actor=actor, detail=detail or None
        )
    )


async def audit_trail(db: AsyncSession, action_ids: list[uuid.UUID]) -> dict[uuid.UUID, list]:
    if not action_ids:
        return {}
    rows = await db.scalars(
        select(ActionAudit)
        .where(ActionAudit.action_id.in_(action_ids))
        .order_by(ActionAudit.created_at, ActionAudit.id)
    )
    trail: dict[uuid.UUID, list] = {i: [] for i in action_ids}
    for r in rows:
        trail[r.action_id].append(
            {"event": r.event, "actor": r.actor, "at": r.created_at, "detail": r.detail or {}}
        )
    return trail


def action_out(a: AgentAction, trail: list | None = None) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "run_id": str(a.run_id),
        "server": a.server,
        "tool": a.tool,
        "arguments": a.arguments,
        "rationale": a.rationale,
        "status": a.status,
        "requested_by": a.requested_by,
        "decided_by": a.decided_by,
        "decided_at": a.decided_at.isoformat() if a.decided_at else None,
        "executed_at": a.executed_at.isoformat() if a.executed_at else None,
        "result": a.result,
        "error": a.error,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "audit": [
            {**e, "at": e["at"].isoformat() if hasattr(e["at"], "isoformat") else e["at"]}
            for e in (trail or [])
        ],
    }

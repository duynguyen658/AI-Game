from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import SessionDependency, get_current_actor
from app.jobs.queue import JobQueue
from app.operations.alert_rules import AlertReconciler
from app.operations.summary import operations_summary
from app.operations.rate_limit import enforce_sensitive_rate_limit
from app.operations.timelines import TimelineService
from app.outbox.dispatcher import OutboxDispatcher
from app.schemas.operations import OperationsSummary, TimelineEvent
from app.service.action_service import ActionService
from app.service.auth_service import AuthService, AuthenticatedActor

router = APIRouter(prefix="/operations", tags=["Operations"])


@router.get("/summary", response_model=OperationsSummary)
async def get_operations_summary(
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> OperationsSummary:
    AuthService().require_operator(actor)
    return await operations_summary(session)


@router.get("/workflows/{workflow_id}/timeline", response_model=list[TimelineEvent])
async def get_workflow_timeline(
    workflow_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[TimelineEvent]:
    return await TimelineService(session).workflow(workflow_id, limit=limit)


@router.get("/campaigns/{campaign_id}/timeline", response_model=list[TimelineEvent])
async def get_campaign_timeline(
    campaign_id: str,
    session: SessionDependency,
    _: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[TimelineEvent]:
    return await TimelineService(session).campaign(campaign_id, limit=limit)


@router.post("/outbox/reconcile", dependencies=[Depends(enforce_sensitive_rate_limit)])
async def reconcile_outbox(
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, int]:
    AuthService().require_operator(actor)
    processed = await OutboxDispatcher(f"operator:{actor.actor_id}").dispatch_once(
        limit=limit
    )
    return {"processed": processed}


@router.post("/memory/reconcile", dependencies=[Depends(enforce_sensitive_rate_limit)])
async def reconcile_memory(
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> dict[str, int]:
    AuthService().require_operator(actor)
    results = await ActionService(session).reconcile_pending_action_memories(
        limit=limit
    )
    return {"processed": len(results)}


@router.post("/jobs/reconcile", dependencies=[Depends(enforce_sensitive_rate_limit)])
async def reconcile_jobs(
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> dict[str, int]:
    AuthService().require_operator(actor)
    jobs = await JobQueue(session).reclaim_stale(limit=limit)
    return {"reclaimed": len(jobs)}


@router.post("/alerts/reconcile", dependencies=[Depends(enforce_sensitive_rate_limit)])
async def reconcile_alerts(
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> dict[str, int]:
    AuthService().require_operator(actor)
    return await AlertReconciler(session).reconcile(limit=limit)

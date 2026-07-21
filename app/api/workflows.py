from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import SessionDependency, get_current_actor
from app.core.constants import JobType, UserRole
from app.jobs.definitions import WorkflowRunJobPayload
from app.jobs.queue import JobQueue
from app.operations.rate_limit import enforce_sensitive_rate_limit
from app.schemas.job import WorkflowEnqueueResponse
from app.schemas.workflow_run import WorkflowRun
from app.security.resource_access import ResourceAccessService
from app.service.auth_service import AuthenticatedActor
from app.service.workflow_service import WorkflowService

router = APIRouter(prefix="/workflows", tags=["Workflows"])


@router.post("/campaigns/{campaign_id}", response_model=WorkflowRun, status_code=201)
async def create_workflow(
    campaign_id: str,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> WorkflowRun:
    await ResourceAccessService(session).require_campaign_access(
        actor, campaign_id, write=True
    )
    return await WorkflowService(session).create_workflow(campaign_id)


@router.get("", response_model=list[WorkflowRun])
async def list_workflows(
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    campaign_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[WorkflowRun]:
    if campaign_id is not None:
        await ResourceAccessService(session).require_campaign_access(actor, campaign_id)
    owner_id = (
        None if actor.role in {UserRole.MANAGER, UserRole.ADMIN} else actor.actor_id
    )
    reviewable_only = actor.role == UserRole.REVIEWER
    if reviewable_only:
        owner_id = None
    return await WorkflowService(session).list_workflows(
        campaign_id=campaign_id,
        limit=limit,
        offset=offset,
        owner_id=owner_id,
        reviewable_only=reviewable_only,
    )


@router.get("/{workflow_id}", response_model=WorkflowRun)
async def get_workflow(
    workflow_id: UUID,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> WorkflowRun:
    await ResourceAccessService(session).require_workflow_access(actor, workflow_id)
    return await WorkflowService(session).get_workflow(workflow_id)


@router.post(
    "/{workflow_id}/run",
    response_model=WorkflowEnqueueResponse,
    status_code=202,
    dependencies=[Depends(enforce_sensitive_rate_limit)],
)
async def run_workflow(
    workflow_id: UUID,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> WorkflowEnqueueResponse:
    await ResourceAccessService(session).require_workflow_access(
        actor, workflow_id, write=True
    )
    job = await JobQueue(session).enqueue(
        JobType.WORKFLOW_RUN,
        WorkflowRunJobPayload(workflow_id=workflow_id),
        created_by=actor.actor_id,
        idempotency_key=JobQueue.build_idempotency_key(
            JobType.WORKFLOW_RUN, {"workflow_id": str(workflow_id)}
        ),
    )
    return WorkflowEnqueueResponse(
        job_id=job.job_id,
        workflow_id=workflow_id,
        status=job.status,
        status_url=f"/jobs/{job.job_id}/status",
        correlation_id=job.correlation_id,
    )

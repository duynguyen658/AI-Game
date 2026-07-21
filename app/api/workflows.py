from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import SessionDependency
from app.core.constants import JobType
from app.jobs.definitions import WorkflowRunJobPayload
from app.jobs.queue import JobQueue
from app.operations.rate_limit import enforce_sensitive_rate_limit
from app.schemas.job import WorkflowEnqueueResponse
from app.schemas.workflow_run import WorkflowRun
from app.service.workflow_service import WorkflowService

router = APIRouter(prefix="/workflows", tags=["Workflows"])


@router.post("/campaigns/{campaign_id}", response_model=WorkflowRun, status_code=201)
async def create_workflow(
    campaign_id: str,
    session: SessionDependency,
) -> WorkflowRun:
    return await WorkflowService(session).create_workflow(campaign_id)


@router.get("/{workflow_id}", response_model=WorkflowRun)
async def get_workflow(
    workflow_id: UUID,
    session: SessionDependency,
) -> WorkflowRun:
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
) -> WorkflowEnqueueResponse:
    await WorkflowService(session).get_workflow(workflow_id)
    job = await JobQueue(session).enqueue(
        JobType.WORKFLOW_RUN,
        WorkflowRunJobPayload(workflow_id=workflow_id),
        created_by="workflow-api",
        idempotency_key=JobQueue.build_idempotency_key(
            JobType.WORKFLOW_RUN, {"workflow_id": str(workflow_id)}
        ),
    )
    return WorkflowEnqueueResponse(
        job_id=job.job_id,
        workflow_id=workflow_id,
        status=job.status,
        status_url=f"/jobs/{job.job_id}",
        correlation_id=job.correlation_id,
    )

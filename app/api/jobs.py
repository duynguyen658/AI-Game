from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import SessionDependency, get_current_actor
from app.core.constants import JobStatus, JobType
from app.jobs.definitions import LeasedJob
from app.jobs.lifecycle import JobTerminalReconciler
from app.jobs.queue import JobQueue
from app.operations.audit import record_operator_action
from app.operations.rate_limit import enforce_sensitive_rate_limit
from app.schemas.job import JobRead, JobStatusRead
from app.service.auth_service import AuthService, AuthenticatedActor

router = APIRouter(prefix="/jobs", tags=["Operations - Jobs"])

USER_VISIBLE_JOB_TYPES = {
    JobType.WORKFLOW_RUN,
    JobType.PROMPT_EXPERIMENT_RUN,
    JobType.PROVIDER_COMPARISON_RUN,
    JobType.IMAGE_GENERATION,
    JobType.DATA_ANALYSIS,
    JobType.DOCUMENT_PROCESSING,
    JobType.VIDEO_STORYBOARD,
}


@router.get("", response_model=list[JobRead])
async def list_jobs(
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: JobStatus | None = None,
    job_type: JobType | None = None,
) -> list[JobRead]:
    AuthService().require_operator(actor)
    return await JobQueue(session).list_jobs(
        limit=limit, offset=offset, status=status, job_type=job_type
    )


@router.get("/{job_id}", response_model=JobRead)
async def get_job(
    job_id: UUID,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> JobRead:
    AuthService().require_operator(actor)
    return await JobQueue(session).get(job_id)


@router.get("/{job_id}/status", response_model=JobStatusRead)
async def get_user_job_status(
    job_id: UUID,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> JobStatusRead:
    job = await JobQueue(session).get(job_id)
    if job.job_type not in USER_VISIBLE_JOB_TYPES:
        AuthService().require_operator(actor)
    return JobStatusRead.model_validate(
        job.model_dump(include=set(JobStatusRead.model_fields))
    )


@router.post(
    "/{job_id}/retry",
    response_model=JobRead,
    dependencies=[Depends(enforce_sensitive_rate_limit)],
)
async def retry_job(
    job_id: UUID,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> JobRead:
    AuthService().require_operator(actor)
    job = await JobQueue(session).retry(job_id)
    await JobTerminalReconciler(session).prepare_retry(_leased_view(job))
    await record_operator_action(
        session,
        actor=actor,
        action="job_retry",
        resource_type="job",
        resource_id=str(job_id),
    )
    return job


@router.post(
    "/{job_id}/cancel",
    response_model=JobRead,
    dependencies=[Depends(enforce_sensitive_rate_limit)],
)
async def cancel_job(
    job_id: UUID,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> JobRead:
    AuthService().require_operator(actor)
    job = await JobQueue(session).cancel(job_id)
    if job.status == JobStatus.CANCELLED:
        await JobTerminalReconciler(session).reconcile(
            _leased_view(job),
            cancelled=True,
            error_code="JOB_CANCELLED",
            error_message="Background job was cancelled",
        )
    await record_operator_action(
        session,
        actor=actor,
        action="job_cancel",
        resource_type="job",
        resource_id=str(job_id),
    )
    return job


def _leased_view(job: JobRead) -> LeasedJob:
    return LeasedJob(
        job_id=job.job_id,
        job_type=job.job_type,
        payload=job.payload,
        attempt_count=max(job.attempt_count, 1),
        max_attempts=max(job.max_attempts, 1),
        correlation_id=job.correlation_id,
        trace_id=job.trace_id,
    )

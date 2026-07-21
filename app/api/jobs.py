from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import SessionDependency, get_current_actor
from app.core.constants import JobStatus, JobType
from app.jobs.queue import JobQueue
from app.operations.audit import record_operator_action
from app.operations.rate_limit import enforce_sensitive_rate_limit
from app.schemas.job import JobRead
from app.service.auth_service import AuthService, AuthenticatedActor

router = APIRouter(prefix="/jobs", tags=["Operations - Jobs"])


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
    await record_operator_action(
        session,
        actor=actor,
        action="job_cancel",
        resource_type="job",
        resource_id=str(job_id),
    )
    return job

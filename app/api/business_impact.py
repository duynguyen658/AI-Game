from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import SessionDependency, get_current_actor
from app.business_impact.service import BusinessImpactService
from app.schemas.business_impact import (
    BusinessImpactAnalytics,
    TaskBaselineCreate,
    TaskBaselineRead,
    TaskImpactCreate,
    TaskImpactRead,
    UserFeedbackCreate,
    UserFeedbackRead,
)
from app.service.auth_service import AuthService, AuthenticatedActor

router = APIRouter(tags=["Applied AI - Business Impact"])


@router.post("/task-baselines", response_model=TaskBaselineRead, status_code=201)
async def create_task_baseline(
    data: TaskBaselineCreate,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> TaskBaselineRead:
    AuthService().require_operator(actor)
    return await BusinessImpactService(session).create_baseline(
        data, actor_id=actor.actor_id
    )


@router.get("/task-baselines", response_model=list[TaskBaselineRead])
async def list_task_baselines(
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TaskBaselineRead]:
    AuthService().require_operator(actor)
    return await BusinessImpactService(session).list_baselines(
        limit=limit, offset=offset
    )


@router.post(
    "/task-runs/{task_run_id}/impact", response_model=TaskImpactRead, status_code=201
)
async def record_task_impact(
    task_run_id: UUID,
    data: TaskImpactCreate,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> TaskImpactRead:
    AuthService().require_operator(actor)
    return await BusinessImpactService(session).record_impact(
        task_run_id, data, actor=actor
    )


@router.post("/task-runs/{task_run_id}/feedback", response_model=UserFeedbackRead)
async def record_task_feedback(
    task_run_id: UUID,
    data: UserFeedbackCreate,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> UserFeedbackRead:
    return await BusinessImpactService(session).record_feedback(
        task_run_id, data, actor=actor
    )


@router.get("/analytics/business-impact", response_model=BusinessImpactAnalytics)
@router.get("/analytics/adoption", response_model=BusinessImpactAnalytics)
@router.get("/analytics/prompt-performance", response_model=BusinessImpactAnalytics)
@router.get("/analytics/provider-performance", response_model=BusinessImpactAnalytics)
async def get_business_impact_analytics(
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    task_type: str | None = None,
    department: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    prompt_version_id: UUID | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> BusinessImpactAnalytics:
    AuthService().require_operator(actor)
    return await BusinessImpactService(session).analytics(
        task_type=task_type,
        department=department,
        provider=provider,
        model=model,
        prompt_version_id=prompt_version_id,
        created_from=created_from,
        created_to=created_to,
    )


@router.get("/analytics/task-types/{task_type}", response_model=BusinessImpactAnalytics)
async def get_task_type_analytics(
    task_type: str,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> BusinessImpactAnalytics:
    AuthService().require_operator(actor)
    return await BusinessImpactService(session).analytics(task_type=task_type)

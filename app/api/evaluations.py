from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import SessionDependency, get_current_actor
from app.evaluation.service import EvaluationService
from app.operations.rate_limit import enforce_sensitive_rate_limit
from app.schemas.evaluation import (
    EvaluationDatasetCreate,
    EvaluationDatasetRead,
    EvaluationRunCreate,
    EvaluationRunRead,
)
from app.service.auth_service import AuthService, AuthenticatedActor

router = APIRouter(prefix="/evaluations", tags=["Operations - Evaluations"])


@router.post(
    "/datasets",
    response_model=EvaluationDatasetRead,
    status_code=201,
    dependencies=[Depends(enforce_sensitive_rate_limit)],
)
async def create_evaluation_dataset(
    data: EvaluationDatasetCreate,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> EvaluationDatasetRead:
    AuthService().require_operator(actor)
    return await EvaluationService(session).create_dataset(
        data, actor_id=actor.actor_id
    )


@router.post(
    "",
    response_model=EvaluationRunRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(enforce_sensitive_rate_limit)],
)
async def create_evaluation_run(
    data: EvaluationRunCreate,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> EvaluationRunRead:
    AuthService().require_operator(actor)
    return await EvaluationService(session).request_run(
        data.dataset_id,
        execution_mode=data.execution_mode,
        actor_id=actor.actor_id,
    )


@router.get("", response_model=list[EvaluationRunRead])
async def list_evaluation_runs(
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[EvaluationRunRead]:
    AuthService().require_operator(actor)
    return await EvaluationService(session).list(limit=limit, offset=offset)


@router.get("/{evaluation_run_id}", response_model=EvaluationRunRead)
async def get_evaluation_run(
    evaluation_run_id: UUID,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> EvaluationRunRead:
    AuthService().require_operator(actor)
    return await EvaluationService(session).get(evaluation_run_id)

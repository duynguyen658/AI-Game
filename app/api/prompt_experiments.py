from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import SessionDependency, get_current_actor
from app.prompt_management.service import PromptService
from app.schemas.prompt import (
    PromptExperimentCreate,
    PromptExperimentCaseRead,
    PromptExperimentRead,
    PromptExperimentRun,
)
from app.service.auth_service import AuthService, AuthenticatedActor

router = APIRouter(
    prefix="/prompt-experiments", tags=["Applied AI - Prompt Experiments"]
)


@router.get("", response_model=list[PromptExperimentRead])
async def list_prompt_experiments(
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[PromptExperimentRead]:
    AuthService().require_operator(actor)
    return await PromptService(session).list_experiments(limit=limit, offset=offset)


@router.post("", response_model=PromptExperimentRead, status_code=201)
async def create_prompt_experiment(
    data: PromptExperimentCreate,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> PromptExperimentRead:
    return await PromptService(session).create_experiment(data, actor=actor)


@router.get("/{experiment_id}", response_model=PromptExperimentRead)
async def get_prompt_experiment(
    experiment_id: UUID,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> PromptExperimentRead:
    AuthService().require_operator(actor)
    return await PromptService(session).get_experiment(experiment_id)


@router.get("/{experiment_id}/results", response_model=list[PromptExperimentCaseRead])
async def get_prompt_experiment_results(
    experiment_id: UUID,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> list[PromptExperimentCaseRead]:
    AuthService().require_operator(actor)
    return await PromptService(session).experiment_cases(experiment_id)


@router.post(
    "/{experiment_id}/run", response_model=PromptExperimentRead, status_code=202
)
async def run_prompt_experiment(
    experiment_id: UUID,
    data: PromptExperimentRun,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> PromptExperimentRead:
    return await PromptService(session).run_experiment(experiment_id, data, actor=actor)


@router.post("/{experiment_id}/cancel", response_model=PromptExperimentRead)
async def cancel_prompt_experiment(
    experiment_id: UUID,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> PromptExperimentRead:
    return await PromptService(session).cancel_experiment(experiment_id, actor=actor)

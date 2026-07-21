from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import SessionDependency, get_current_actor
from app.core.constants import PromptVersionStatus
from app.operations.rate_limit import enforce_sensitive_rate_limit
from app.prompt_management.service import PromptService
from app.schemas.prompt import (
    ExpectedVersionRequest,
    PromptActivationRequest,
    PromptRollbackRequest,
    PromptTemplateCreate,
    PromptTemplateRead,
    PromptVersionCreate,
    PromptVersionRead,
)
from app.service.auth_service import AuthenticatedActor

router = APIRouter(tags=["Applied AI - Prompts"])


@router.get("/prompt-templates", response_model=list[PromptTemplateRead])
async def list_prompt_templates(
    session: SessionDependency,
    _: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[PromptTemplateRead]:
    return await PromptService(session).list_templates(limit=limit, offset=offset)


@router.post(
    "/prompt-templates",
    response_model=PromptTemplateRead,
    status_code=201,
    dependencies=[Depends(enforce_sensitive_rate_limit)],
)
async def create_prompt_template(
    data: PromptTemplateCreate,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> PromptTemplateRead:
    return await PromptService(session).create_template(data, actor=actor)


@router.get("/prompt-templates/{template_id}", response_model=PromptTemplateRead)
async def get_prompt_template(
    template_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> PromptTemplateRead:
    return await PromptService(session).get_template(template_id)


@router.post(
    "/prompt-templates/{template_id}/versions",
    response_model=PromptVersionRead,
    status_code=201,
)
async def create_prompt_version(
    template_id: UUID,
    data: PromptVersionCreate,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> PromptVersionRead:
    return await PromptService(session).create_version(template_id, data, actor=actor)


@router.get("/prompt-versions/{version_id}", response_model=PromptVersionRead)
async def get_prompt_version(
    version_id: UUID,
    session: SessionDependency,
    _: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> PromptVersionRead:
    return await PromptService(session).get_version(version_id)


async def _transition(
    version_id: UUID,
    data: ExpectedVersionRequest,
    target: PromptVersionStatus,
    session: SessionDependency,
    actor: AuthenticatedActor,
) -> PromptVersionRead:
    return await PromptService(session).transition(
        version_id, target, expected_status=data.expected_status, actor=actor
    )


@router.post(
    "/prompt-versions/{version_id}/submit-testing", response_model=PromptVersionRead
)
async def submit_prompt_testing(
    version_id: UUID,
    data: ExpectedVersionRequest,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> PromptVersionRead:
    return await _transition(
        version_id, data, PromptVersionStatus.TESTING, session, actor
    )


@router.post("/prompt-versions/{version_id}/approve", response_model=PromptVersionRead)
async def approve_prompt_version(
    version_id: UUID,
    data: ExpectedVersionRequest,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> PromptVersionRead:
    return await _transition(
        version_id, data, PromptVersionStatus.APPROVED, session, actor
    )


@router.post("/prompt-versions/{version_id}/activate", response_model=PromptVersionRead)
async def activate_prompt_version(
    version_id: UUID,
    data: PromptActivationRequest,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> PromptVersionRead:
    return await PromptService(session).activate(
        version_id,
        expected_status=data.expected_status,
        expected_template_version=data.expected_template_version,
        actor=actor,
    )


@router.post("/prompt-versions/{version_id}/retire", response_model=PromptVersionRead)
async def retire_prompt_version(
    version_id: UUID,
    data: ExpectedVersionRequest,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> PromptVersionRead:
    return await _transition(
        version_id, data, PromptVersionStatus.RETIRED, session, actor
    )


@router.post(
    "/prompt-templates/{template_id}/rollback", response_model=PromptVersionRead
)
async def rollback_prompt_template(
    template_id: UUID,
    data: PromptRollbackRequest,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> PromptVersionRead:
    return await PromptService(session).rollback(
        template_id,
        data.prompt_version_id,
        expected_template_version=data.expected_template_version,
        actor=actor,
    )

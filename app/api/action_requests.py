from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import SessionDependency, get_current_actor
from app.core.constants import ActionRequestStatus
from app.schemas.action_execution import ActionExecutionRead
from app.schemas.action_request import (
    ActionApproveRequest,
    ActionExecuteRequest,
    ActionRejectRequest,
    ActionRequestRead,
)
from app.service.action_service import ActionService
from app.operations.rate_limit import enforce_sensitive_rate_limit
from app.service.auth_service import AuthenticatedActor, AuthService

router = APIRouter(prefix="/action-requests", tags=["Agent Actions"])


@router.get("", response_model=list[ActionRequestRead])
async def list_action_requests(
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    request_status: ActionRequestStatus | None = None,
) -> list[ActionRequestRead]:
    AuthService().require_action_read(actor)
    return await ActionService(session).list_requests(
        limit=limit, offset=offset, status=request_status
    )


@router.get("/{action_request_id}", response_model=ActionRequestRead)
async def get_action_request(
    action_request_id: UUID,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> ActionRequestRead:
    AuthService().require_action_read(actor)
    return await ActionService(session).get(action_request_id)


@router.get("/{action_request_id}/executions", response_model=list[ActionExecutionRead])
async def list_action_executions(
    action_request_id: UUID,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> list[ActionExecutionRead]:
    AuthService().require_action_read(actor)
    return await ActionService(session).list_executions(action_request_id)


@router.post(
    "/{action_request_id}/approve",
    response_model=ActionRequestRead,
    dependencies=[Depends(enforce_sensitive_rate_limit)],
)
async def approve_action_request(
    action_request_id: UUID,
    payload: ActionApproveRequest,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> ActionRequestRead:
    return await ActionService(session).approve(
        action_request_id,
        actor=actor,
        expected_version=payload.expected_version,
    )


@router.post(
    "/{action_request_id}/reject",
    response_model=ActionRequestRead,
    dependencies=[Depends(enforce_sensitive_rate_limit)],
)
async def reject_action_request(
    action_request_id: UUID,
    payload: ActionRejectRequest,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> ActionRequestRead:
    return await ActionService(session).reject(
        action_request_id,
        actor=actor,
        expected_version=payload.expected_version,
        reason=payload.reason,
    )


@router.post(
    "/{action_request_id}/execute",
    response_model=ActionExecutionRead,
    dependencies=[Depends(enforce_sensitive_rate_limit)],
)
async def execute_action_request(
    action_request_id: UUID,
    payload: ActionExecuteRequest,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> ActionExecutionRead:
    return await ActionService(session).execute(
        action_request_id,
        actor=actor,
        expected_version=payload.expected_version,
    )

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import SessionDependency, get_current_actor
from app.core.constants import AppliedTaskStatus, AppliedWorkflowType, UserRole
from app.schemas.applied_workflow import AppliedTaskRead
from app.service.applied_workflow_service import AppliedWorkflowService
from app.service.auth_service import AuthenticatedActor

router = APIRouter(prefix="/applied-workflow-tasks", tags=["Applied AI - Tasks"])


@router.get("", response_model=list[AppliedTaskRead])
async def list_applied_tasks(
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    workflow_type: AppliedWorkflowType | None = None,
    status: AppliedTaskStatus | None = None,
) -> list[AppliedTaskRead]:
    owner_id = (
        None if actor.role in {UserRole.MANAGER, UserRole.ADMIN} else actor.actor_id
    )
    return await AppliedWorkflowService(session).list(
        limit=limit,
        offset=offset,
        owner_id=owner_id,
        workflow_type=workflow_type,
        status=status,
    )

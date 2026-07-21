from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_actor
from app.applied_workflows.definitions import AppliedWorkflowDefinition
from app.applied_workflows.registry import AppliedWorkflowRegistry
from app.core.constants import AppliedWorkflowType
from app.core.exceptions import AuthorizationError
from app.service.auth_service import AuthenticatedActor

router = APIRouter(prefix="/applied-workflows", tags=["Applied AI - Workflow Catalog"])


@router.get("", response_model=list[AppliedWorkflowDefinition])
async def list_applied_workflows(
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> list[AppliedWorkflowDefinition]:
    return [
        item
        for item in AppliedWorkflowRegistry().list()
        if actor.role in item.allowed_roles
    ]


@router.get("/{workflow_type}", response_model=AppliedWorkflowDefinition)
async def get_applied_workflow(
    workflow_type: AppliedWorkflowType,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> AppliedWorkflowDefinition:
    item = AppliedWorkflowRegistry().get(workflow_type)
    if actor.role not in item.allowed_roles:
        raise AuthorizationError("Actor cannot access this workflow")
    return item

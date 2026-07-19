from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import SessionDependency, get_current_actor
from app.schemas.approval import ApprovalRecord, ApprovalRequest
from app.service.approval_service import ApprovalService
from app.service.auth_service import AuthenticatedActor

router = APIRouter(prefix="/approvals", tags=["Approvals"])


@router.post("", response_model=ApprovalRecord, status_code=201)
async def decide_approval(
    payload: ApprovalRequest,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> ApprovalRecord:
    return await ApprovalService(session).decide(
        payload,
        actor_id=actor.actor_id,
        actor_role=actor.role,
    )

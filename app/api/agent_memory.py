from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import SessionDependency, get_current_actor
from app.core.constants import MemoryEventType
from app.schemas.memory_entry import MemoryEntryRead
from app.service.auth_service import AuthenticatedActor, AuthService
from app.service.memory_service import MemoryService

router = APIRouter(tags=["Agent Memory"])


@router.get("/campaigns/{campaign_id}/memories", response_model=list[MemoryEntryRead])
async def list_campaign_memories(
    campaign_id: str,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    event_type: MemoryEventType | None = None,
) -> list[MemoryEntryRead]:
    AuthService().require_action_read(actor)
    return await MemoryService(session).list_campaign(
        campaign_id,
        limit=limit,
        offset=offset,
        event_type=event_type,
    )


@router.get("/workflows/{workflow_id}/memories", response_model=list[MemoryEntryRead])
async def list_workflow_memories(
    workflow_id: UUID,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    event_type: MemoryEventType | None = None,
) -> list[MemoryEntryRead]:
    AuthService().require_action_read(actor)
    return await MemoryService(session).list_workflow(
        workflow_id,
        limit=limit,
        offset=offset,
        event_type=event_type,
    )

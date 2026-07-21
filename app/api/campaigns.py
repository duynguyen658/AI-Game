from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import SessionDependency, get_current_actor
from app.core.constants import CampaignStatus, UserRole
from app.security.resource_access import ResourceAccessService
from app.schemas.campaign import CampaignCreate, CampaignRecord
from app.service.auth_service import AuthenticatedActor
from app.service.campaign_service import CampaignService

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])


@router.post("", response_model=CampaignRecord, status_code=201)
async def create_campaign(
    payload: CampaignCreate,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> CampaignRecord:
    return await CampaignService(session).create_campaign(
        payload, created_by=actor.actor_id
    )


@router.get("", response_model=list[CampaignRecord])
async def list_campaigns(
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: CampaignStatus | None = None,
) -> list[CampaignRecord]:
    owner_id = (
        None if actor.role in {UserRole.MANAGER, UserRole.ADMIN} else actor.actor_id
    )
    reviewable_only = actor.role == UserRole.REVIEWER
    if reviewable_only:
        owner_id = None
    return await CampaignService(session).list_campaigns(
        limit=limit,
        offset=offset,
        status=status,
        owner_id=owner_id,
        reviewable_only=reviewable_only,
    )


@router.get("/{campaign_id}", response_model=CampaignRecord)
async def get_campaign(
    campaign_id: str,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> CampaignRecord:
    await ResourceAccessService(session).require_campaign_access(actor, campaign_id)
    return await CampaignService(session).get_campaign(campaign_id)


@router.put("/{campaign_id}", response_model=CampaignRecord)
async def update_campaign(
    campaign_id: str,
    payload: CampaignCreate,
    session: SessionDependency,
    actor: Annotated[AuthenticatedActor, Depends(get_current_actor)],
) -> CampaignRecord:
    await ResourceAccessService(session).require_campaign_access(
        actor, campaign_id, write=True
    )
    return await CampaignService(session).update_campaign(campaign_id, payload)

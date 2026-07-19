from typing import Annotated

from fastapi import APIRouter, Query

from app.api.dependencies import SessionDependency
from app.core.constants import CampaignStatus
from app.schemas.campaign import CampaignCreate, CampaignRecord
from app.service.campaign_service import CampaignService

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])


@router.post("", response_model=CampaignRecord, status_code=201)
async def create_campaign(
    payload: CampaignCreate,
    session: SessionDependency,
) -> CampaignRecord:
    return await CampaignService(session).create_campaign(payload)


@router.get("", response_model=list[CampaignRecord])
async def list_campaigns(
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: CampaignStatus | None = None,
) -> list[CampaignRecord]:
    return await CampaignService(session).list_campaigns(
        limit=limit,
        offset=offset,
        status=status,
    )


@router.get("/{campaign_id}", response_model=CampaignRecord)
async def get_campaign(
    campaign_id: str,
    session: SessionDependency,
) -> CampaignRecord:
    return await CampaignService(session).get_campaign(campaign_id)


@router.put("/{campaign_id}", response_model=CampaignRecord)
async def update_campaign(
    campaign_id: str,
    payload: CampaignCreate,
    session: SessionDependency,
) -> CampaignRecord:
    return await CampaignService(session).update_campaign(campaign_id, payload)

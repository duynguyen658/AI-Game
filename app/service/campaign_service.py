from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import CampaignStatus
from app.core.exceptions import (
    CampaignAlreadyExistsError,
    CampaignNotFoundError,
    CampaignValidationError,
)
from app.repositories.campaign_repository import CampaignRepository
from app.schemas.campaign import CampaignCreate, CampaignRecord
from app.service.mappers import campaign_to_record


class CampaignService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = CampaignRepository(session)

    async def create_campaign(self, payload: CampaignCreate) -> CampaignRecord:
        if await self.repository.exists(payload.campaign_id):
            raise CampaignAlreadyExistsError("Campaign already exists")
        try:
            model = await self.repository.create(payload)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise CampaignAlreadyExistsError("Campaign already exists") from exc
        except Exception:
            await self.session.rollback()
            raise
        return campaign_to_record(model)

    async def get_campaign(self, campaign_id: str) -> CampaignRecord:
        model = await self.repository.get_by_id(campaign_id)
        if model is None:
            raise CampaignNotFoundError("Campaign not found")
        return campaign_to_record(model)

    async def list_campaigns(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        status: CampaignStatus | None = None,
    ) -> list[CampaignRecord]:
        bounded_limit = min(max(limit, 1), 100)
        bounded_offset = max(offset, 0)
        models = await self.repository.list(
            limit=bounded_limit,
            offset=bounded_offset,
            status=status,
        )
        return [campaign_to_record(model) for model in models]

    async def update_campaign(
        self,
        campaign_id: str,
        payload: CampaignCreate,
    ) -> CampaignRecord:
        if campaign_id != payload.campaign_id:
            raise CampaignValidationError("Campaign ID cannot be changed")
        model = await self.repository.get_by_id_for_update(campaign_id)
        if model is None:
            raise CampaignNotFoundError("Campaign not found")
        await self.repository.update_allowed_fields(model, payload)
        await self.repository.increment_version(model)
        await self.session.commit()
        return campaign_to_record(model)

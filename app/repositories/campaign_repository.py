from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import CampaignStatus, Platform
from app.database.models import CampaignModel
from app.schemas.campaign import (
    BriefAnalysis,
    CampaignCreate,
    GeneratedContent,
    QualityReview,
    CampaignMetadataUpdate,
)


class CampaignRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        payload: CampaignCreate,
        *,
        created_by: str = "system",
        evaluation_run_id: UUID | None = None,
        evaluation_case_id: UUID | None = None,
    ) -> CampaignModel:
        model = CampaignModel(
            campaign_id=payload.campaign_id,
            game_name=payload.game_name,
            genre=payload.genre,
            target_audience=payload.target_audience,
            market=payload.market,
            platforms=[platform.value for platform in payload.platforms],
            campaign_objective=payload.campaign_objective,
            tone=payload.tone,
            launch_date=payload.launch_date,
            promotion=payload.promotion,
            raw_brief=payload.raw_brief,
            created_by=created_by,
            status=CampaignStatus.RECEIVED.value,
            is_evaluation=evaluation_run_id is not None,
            evaluation_run_id=evaluation_run_id,
            evaluation_case_id=evaluation_case_id,
        )
        self.session.add(model)
        await self.session.flush()
        return model

    async def get_by_id(self, campaign_id: str) -> CampaignModel | None:
        return await self.session.get(CampaignModel, campaign_id)

    async def get_by_id_for_update(self, campaign_id: str) -> CampaignModel | None:
        result = await self.session.execute(
            select(CampaignModel)
            .where(CampaignModel.campaign_id == campaign_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def exists(self, campaign_id: str) -> bool:
        result = await self.session.execute(
            select(func.count())
            .select_from(CampaignModel)
            .where(CampaignModel.campaign_id == campaign_id)
        )
        return result.scalar_one() > 0

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        status: CampaignStatus | None = None,
        owner_id: str | None = None,
        reviewable_only: bool = False,
    ) -> Sequence[CampaignModel]:
        query: Select[tuple[CampaignModel]] = select(CampaignModel)
        query = query.where(CampaignModel.is_evaluation.is_(False))
        if status is not None:
            query = query.where(CampaignModel.status == status.value)
        if owner_id is not None:
            query = query.where(CampaignModel.created_by == owner_id)
        if reviewable_only:
            query = query.where(
                CampaignModel.status.in_(
                    [
                        CampaignStatus.REVIEWING.value,
                        CampaignStatus.MANUAL_REVIEW_REQUIRED.value,
                        CampaignStatus.PENDING_APPROVAL.value,
                    ]
                )
            )
        query = (
            query.order_by(CampaignModel.created_at.desc()).limit(limit).offset(offset)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def update_status(
        self,
        campaign: CampaignModel,
        status: CampaignStatus,
    ) -> CampaignModel:
        campaign.status = status.value
        await self.session.flush()
        return campaign

    async def save_brief_analysis(
        self,
        campaign: CampaignModel,
        analysis: BriefAnalysis,
    ) -> CampaignModel:
        campaign.brief_analysis = analysis.model_dump(mode="json")
        await self.session.flush()
        return campaign

    async def save_generated_content(
        self,
        campaign: CampaignModel,
        content: GeneratedContent,
    ) -> CampaignModel:
        campaign.generated_content = content.model_dump(mode="json")
        await self.session.flush()
        return campaign

    async def save_quality_review(
        self,
        campaign: CampaignModel,
        review: QualityReview,
    ) -> CampaignModel:
        campaign.quality_review = review.model_dump(mode="json")
        campaign.quality_score = review.quality_score
        await self.session.flush()
        return campaign

    async def increment_retry_count(self, campaign: CampaignModel) -> CampaignModel:
        campaign.retry_count += 1
        await self.session.flush()
        return campaign

    async def increment_version(self, campaign: CampaignModel) -> CampaignModel:
        campaign.version += 1
        await self.session.flush()
        return campaign

    async def update_allowed_fields(
        self,
        campaign: CampaignModel,
        payload: CampaignCreate,
    ) -> CampaignModel:
        campaign.game_name = payload.game_name
        campaign.genre = payload.genre
        campaign.target_audience = payload.target_audience
        campaign.market = payload.market
        campaign.platforms = [platform.value for platform in payload.platforms]
        campaign.campaign_objective = payload.campaign_objective
        campaign.tone = payload.tone
        campaign.launch_date = payload.launch_date
        campaign.promotion = payload.promotion
        campaign.raw_brief = payload.raw_brief
        await self.session.flush()
        return campaign

    async def update_metadata(
        self, campaign: CampaignModel, payload: CampaignMetadataUpdate
    ) -> CampaignModel:
        if payload.tone is not None:
            campaign.tone = payload.tone
        if payload.target_audience is not None:
            campaign.target_audience = payload.target_audience
        if payload.promotion is not None:
            campaign.promotion = payload.promotion
        await self.session.flush()
        return campaign


def platform_values_to_enums(values: list[str]) -> list[Platform]:
    return [Platform(value) for value in values]

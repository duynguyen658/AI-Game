from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.constants import CampaignStatus, Platform
from app.schemas.campaign import BriefAnalysis, GeneratedContent, QualityReview


class CampaignContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    campaign_id: str
    workflow_id: UUID
    revision_number: int
    current_workflow_status: CampaignStatus
    retry_count: int
    parent_workflow_id: UUID | None = None


class BriefAnalysisContext(CampaignContext):
    game_name: str
    genre: str
    target_audience: str
    market: str
    platforms: tuple[Platform, ...]
    campaign_objective: str
    tone: str
    launch_date: date
    promotion: str
    raw_brief: str | None


class ContentGenerationContext(CampaignContext):
    game_name: str
    target_audience: str
    market: str
    platforms: tuple[Platform, ...]
    campaign_objective: str
    tone: str
    launch_date: date
    promotion: str
    raw_brief: str | None
    brief_analysis: BriefAnalysis
    prior_generated_content: GeneratedContent | None = None
    prior_quality_review: QualityReview | None = None


class ContentReviewContext(CampaignContext):
    campaign_objective: str
    platforms: tuple[Platform, ...]
    tone: str
    brief_analysis: BriefAnalysis
    generated_content: GeneratedContent
    prior_quality_review: QualityReview | None = None

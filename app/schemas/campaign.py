from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.constants import CampaignStatus, SUPPORTED_PLATFORMS


class CampaignCreate(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    campaign_id: str = Field(min_length=1, max_length=100)
    game_name: str = Field(min_length=1, max_length=200)
    genre: str = Field(min_length=1, max_length=100)
    target_audience: str = Field(min_length=1, max_length=300)
    market: str = Field(min_length=1, max_length=100)
    platforms: list[str] = Field(min_length=1)
    campaign_objective: str = Field(min_length=1, max_length=1000)
    tone: str = Field(min_length=1, max_length=500)
    launch_date: date
    promotion: str = Field(min_length=1, max_length=1000)
    raw_brief: str = Field(default="", max_length=20_000)

    @field_validator("platforms")
    @classmethod
    def validate_platforms(cls, platforms: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(platforms))

        unsupported = [
            platform
            for platform in normalized
            if platform not in SUPPORTED_PLATFORMS
        ]

        if unsupported:
            raise ValueError(
                f"Unsupported platforms: {', '.join(unsupported)}"
            )

        return normalized


class BriefAnalysis(BaseModel):
    summary: str
    campaign_objective: str
    target_audience: str
    main_message: str
    key_benefits: list[str]
    content_requirements: list[str]
    missing_information: list[str]
    risk_flags: list[str]


class PlatformContent(BaseModel):
    headline: str
    content: str
    cta: str
    hashtags: list[str]


class GeneratedContent(BaseModel):
    facebook: PlatformContent | None = None
    tiktok: PlatformContent | None = None
    discord: PlatformContent | None = None


class QualityReview(BaseModel):
    status: str
    quality_score: int = Field(ge=0, le=100)
    factual_accuracy_score: int = Field(ge=0, le=100)
    tone_score: int = Field(ge=0, le=100)
    platform_fit_score: int = Field(ge=0, le=100)
    issues: list[str]
    suggestions: list[str]
    requires_human_review: bool = True


class CampaignRecord(BaseModel):
    campaign: CampaignCreate
    status: CampaignStatus
    analysis: BriefAnalysis | None = None
    generated_content: GeneratedContent | None = None
    quality_review: QualityReview | None = None
    retry_count: int = 0
    created_at: datetime
    updated_at: datetime
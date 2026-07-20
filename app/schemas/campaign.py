from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.constants import (
    CAMPAIGN_ID_PATTERN,
    MAX_CAMPAIGN_ID_LENGTH,
    MAX_RAW_BRIEF_LENGTH,
    MIN_CAMPAIGN_ID_LENGTH,
    CampaignStatus,
    Platform,
)


class StrictSchema(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )


class CampaignCreate(StrictSchema):
    campaign_id: str = Field(
        min_length=MIN_CAMPAIGN_ID_LENGTH,
        max_length=MAX_CAMPAIGN_ID_LENGTH,
        pattern=CAMPAIGN_ID_PATTERN,
    )
    game_name: str = Field(
        min_length=1,
        max_length=200,
    )
    genre: str = Field(
        min_length=1,
        max_length=100,
    )
    target_audience: str = Field(
        min_length=1,
        max_length=300,
    )
    market: str = Field(
        min_length=1,
        max_length=100,
    )
    platforms: list[Platform] = Field(
        min_length=1,
        max_length=3,
    )
    campaign_objective: str = Field(
        min_length=1,
        max_length=1000,
    )
    tone: str = Field(
        min_length=1,
        max_length=500,
    )
    launch_date: date
    promotion: str = Field(
        min_length=1,
        max_length=1000,
    )
    raw_brief: str | None = Field(
        default=None,
        max_length=MAX_RAW_BRIEF_LENGTH,
    )

    @field_validator("platforms", mode="before")
    @classmethod
    def normalize_platforms(cls, value: object) -> object:
        if not isinstance(value, list):
            raise ValueError("platforms must be a list")
        platform_mapping = {
            "facebook": Platform.FACEBOOK,
            "tiktok": Platform.TIKTOK,
            "discord": Platform.DISCORD,
        }
        normalized: list[object] = []
        for item in value:
            if isinstance(item, Platform):
                platform: object = item
            elif isinstance(item, str):
                normalized_name = item.strip().lower()

                platform = platform_mapping.get(
                    normalized_name,
                    item.strip(),
                )
            else:
                platform = item
            if platform not in normalized:
                normalized.append(platform)
        return normalized

    @field_validator("raw_brief")
    @classmethod
    def normalize_raw_brief(
        cls,
        value: str | None,
    ) -> str | None:
        if value == "":
            return None
        return value


class CampaignMetadataUpdate(StrictSchema):
    tone: str | None = Field(default=None, min_length=1, max_length=500)
    target_audience: str | None = Field(default=None, min_length=1, max_length=300)
    promotion: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def require_change(self) -> "CampaignMetadataUpdate":
        if not any(
            value is not None
            for value in (self.tone, self.target_audience, self.promotion)
        ):
            raise ValueError("At least one metadata field is required")
        return self


class BriefAnalysis(StrictSchema):
    summary: str = Field(
        min_length=1,
        max_length=3000,
    )
    campaign_objective: str = Field(
        min_length=1,
        max_length=1000,
    )
    target_audience: str = Field(
        min_length=1,
        max_length=1000,
    )
    main_message: str = Field(
        min_length=1,
        max_length=2000,
    )
    key_benefits: list[str] = Field(
        default_factory=list,
    )
    content_requirements: list[str] = Field(
        default_factory=list,
    )
    missing_information: list[str] = Field(
        default_factory=list,
    )
    risk_flags: list[str] = Field(
        default_factory=list,
    )


class FacebookContent(StrictSchema):
    headline: str = Field(
        min_length=1,
        max_length=200,
    )
    content: str = Field(
        min_length=1,
        max_length=5000,
    )
    cta: str = Field(
        min_length=1,
        max_length=500,
    )
    hashtags: list[str] = Field(
        default_factory=list,
        max_length=20,
    )


class TikTokScene(StrictSchema):
    order: int = Field(
        ge=1,
    )
    duration_seconds: float = Field(
        gt=0,
        le=60,
    )
    visual: str = Field(
        min_length=1,
        max_length=1000,
    )
    text_overlay: str | None = Field(
        default=None,
        max_length=500,
    )


class TikTokContent(StrictSchema):
    hook: str = Field(
        min_length=1,
        max_length=500,
    )
    scenes: list[TikTokScene] = Field(
        min_length=1,
        max_length=20,
    )
    voiceover: str = Field(
        min_length=1,
        max_length=5000,
    )
    cta: str = Field(
        min_length=1,
        max_length=500,
    )


class DiscordContent(StrictSchema):
    title: str = Field(
        min_length=1,
        max_length=200,
    )
    message: str = Field(
        min_length=1,
        max_length=3000,
    )
    cta: str = Field(
        min_length=1,
        max_length=500,
    )


class GeneratedContent(StrictSchema):
    facebook: FacebookContent | None = None
    tiktok: TikTokContent | None = None
    discord: DiscordContent | None = None


class QualityReview(StrictSchema):
    status: Literal[
        "PASS",
        "FAIL",
        "MANUAL_REVIEW_REQUIRED",
    ]
    quality_score: int = Field(
        ge=0,
        le=100,
    )
    factual_accuracy_score: int = Field(
        ge=0,
        le=100,
    )
    tone_score: int = Field(
        ge=0,
        le=100,
    )
    platform_fit_score: int = Field(
        ge=0,
        le=100,
    )
    issues: list[str] = Field(
        default_factory=list,
    )
    suggestions: list[str] = Field(
        default_factory=list,
    )
    requires_human_review: bool = True


class CampaignRecord(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        validate_assignment=True,
    )
    campaign: CampaignCreate
    status: CampaignStatus = CampaignStatus.RECEIVED
    analysis: BriefAnalysis | None = None
    generated_content: GeneratedContent | None = None
    quality_review: QualityReview | None = None
    retry_count: int = Field(
        default=0,
        ge=0,
    )
    version: int = Field(
        default=1,
        ge=1,
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )

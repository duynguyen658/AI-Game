from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import MediaAssetStatus, MediaAssetType


class ImageGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_id: str | None = Field(default=None, max_length=100)
    workflow_id: UUID | None = None
    task_type: str = Field(default="campaign_image", min_length=1, max_length=100)
    prompt: str = Field(min_length=1, max_length=10_000)
    negative_prompt: str | None = Field(default=None, max_length=3000)
    width: int = Field(default=1024, ge=256, le=2048)
    height: int = Field(default=1024, ge=256, le=2048)


class MediaReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["APPROVE", "REJECT"]
    rating: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class MediaAssetRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    media_asset_id: UUID
    campaign_id: str | None
    workflow_id: UUID | None
    task_run_id: UUID | None
    task_type: str
    asset_type: MediaAssetType
    status: MediaAssetStatus
    provider: str
    model: str
    prompt_version_id: UUID | None
    generation_prompt: str
    negative_prompt: str | None
    storage_uri: str | None
    thumbnail_uri: str | None
    mime_type: str | None
    width: int | None
    height: int | None
    duration_seconds: int | None
    estimated_cost: Decimal | None
    safety_status: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    approved_by: str | None
    approved_at: datetime | None
    rejected_by: str | None
    rejected_at: datetime | None
    rejection_reason: str | None


class VideoStoryboardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_id: str | None = Field(default=None, max_length=100)
    campaign_brief: str = Field(min_length=1, max_length=20_000)
    objective: str = Field(min_length=1, max_length=1000)
    target_duration_seconds: int = Field(default=30, ge=5, le=300)
    aspect_ratio: Literal["16:9", "9:16", "1:1"] = "16:9"


class StoryboardScene(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: int = Field(ge=1)
    duration_seconds: int = Field(ge=1, le=120)
    shot_description: str
    voice_over: str
    on_screen_text: str
    generation_prompt: str


class VideoStoryboard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    objective: str
    target_duration_seconds: int
    aspect_ratio: str
    scenes: list[StoryboardScene]
    voice_over: str
    music_mood: str
    call_to_action: str
    provider_prompt: str

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.constants import CampaignStatus, Platform


class CampaignContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    campaign_id: str
    workflow_id: UUID
    revision_number: int
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
    current_workflow_status: CampaignStatus
    retry_count: int
    brief_analysis: dict[str, Any] | None = None
    generated_content: dict[str, Any] | None = None
    quality_review: dict[str, Any] | None = None
    parent_workflow_id: UUID | None = None

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.core.constants import CampaignStatus


class WorkflowRun(BaseModel):
    workflow_id: UUID = Field(default_factory=uuid4)
    campaign_id: str
    status: CampaignStatus
    current_step: str
    llm_call_count: int = 0
    retry_count: int = 0
    quality_score: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime
    completed_at: datetime | None = None

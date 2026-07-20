from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import (
    ActionExecutionStatus,
    CampaignStatus,
    MemoryRecordStatus,
)


class ActionExecutionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_execution_id: UUID
    action_request_id: UUID
    status: ActionExecutionStatus
    attempt_number: int = Field(ge=1)
    idempotency_key: str = Field(min_length=64, max_length=64)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    result_summary: str | None = Field(default=None, max_length=12_000)
    error_code: str | None = Field(default=None, max_length=100)
    error_message: str | None = Field(default=None, max_length=2000)
    reserved_campaign_status: CampaignStatus | None = None
    reserved_campaign_version: int | None = Field(default=None, ge=1)
    reserved_workflow_status: CampaignStatus | None = None
    reserved_revision_number: int | None = Field(default=None, ge=0)
    memory_record_status: MemoryRecordStatus
    memory_record_attempts: int = Field(ge=0)
    memory_record_error_code: str | None = Field(default=None, max_length=100)
    memory_record_error_message: str | None = Field(default=None, max_length=2000)
    memory_recorded_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

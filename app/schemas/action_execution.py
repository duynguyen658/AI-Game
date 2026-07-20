from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import ActionExecutionStatus


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
    created_at: datetime
    updated_at: datetime

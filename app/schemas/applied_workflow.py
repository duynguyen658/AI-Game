from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.constants import AppliedTaskStatus, AppliedWorkflowType


class AppliedTaskRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_run_id: UUID
    workflow_type: AppliedWorkflowType
    status: AppliedTaskStatus
    input_metadata: dict[str, Any]
    result: dict[str, Any] | None
    prompt_version_id: UUID | None
    prompt_template_id: UUID | None
    prompt_version_number: int | None
    prompt_content_hash: str | None
    provider: str | None
    model: str | None
    model_configuration_hash: str | None
    application_version: str | None
    job_id: UUID | None
    error_code: str | None
    error_message: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    started_at: datetime | None
    duration_ms: int | None
    input_tokens: int
    output_tokens: int
    estimated_cost: Decimal

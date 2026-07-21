from __future__ import annotations

from datetime import datetime
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
    provider: str | None
    model: str | None
    job_id: UUID | None
    error_code: str | None
    error_message: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

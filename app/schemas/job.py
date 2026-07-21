from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import JobAttemptStatus, JobStatus, JobType


class JobAttemptRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_attempt_id: UUID
    attempt_number: int = Field(ge=1)
    worker_id: str
    status: JobAttemptStatus
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    error_code: str | None = None
    error_message: str | None = None


class JobRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: UUID
    job_type: JobType
    status: JobStatus
    payload: dict[str, Any]
    priority: int = Field(ge=0, le=100)
    attempt_count: int = Field(ge=0)
    max_attempts: int = Field(ge=1)
    available_at: datetime
    locked_by: str | None = None
    lease_expires_at: datetime | None = None
    heartbeat_at: datetime | None = None
    cancel_requested: bool
    idempotency_key: str
    correlation_id: str
    trace_id: str | None = None
    created_by: str
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    attempts: list[JobAttemptRead] = Field(default_factory=list)


class WorkflowEnqueueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: UUID
    workflow_id: UUID
    status: JobStatus
    status_url: str
    correlation_id: str

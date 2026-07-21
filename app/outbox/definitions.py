from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import OutboxEventType


class OutboxEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    outbox_event_id: UUID
    event_type: OutboxEventType
    aggregate_type: str = Field(min_length=1, max_length=100)
    aggregate_id: str = Field(min_length=1, max_length=200)
    payload: dict[str, Any]
    attempt_count: int = Field(ge=1)
    max_attempts: int = Field(ge=1)
    lease_version: int = Field(ge=1)
    correlation_id: str
    trace_id: str | None = None

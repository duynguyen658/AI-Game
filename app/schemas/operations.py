from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OperationsSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    jobs: dict[str, int]
    alerts: dict[str, int]
    workflows: dict[str, int]
    actions: dict[str, int]
    evaluations: dict[str, int]
    outbox: dict[str, int]
    fresh_workers: int
    generated_at: datetime


class TimelineEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    occurred_at: datetime
    event_type: str
    resource_type: str
    resource_id: str
    status: str | None = None
    summary: str
    correlation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

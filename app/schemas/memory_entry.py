from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import MemoryEventType, MemoryType


class MemoryEntryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_id: str = Field(min_length=3, max_length=100)
    workflow_id: UUID | None = None
    agent_run_id: UUID | None = None
    action_request_id: UUID | None = None
    action_execution_id: UUID | None = None
    memory_type: MemoryType = MemoryType.EPISODIC
    event_type: MemoryEventType
    summary: str = Field(min_length=1, max_length=3000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    importance: int = Field(default=3, ge=1, le=5)
    expires_at: datetime | None = None


class MemoryEntryRead(MemoryEntryCreate):
    memory_entry_id: UUID
    created_at: datetime

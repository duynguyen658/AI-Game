from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import ToolCallStatus


class ToolCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_run_id: UUID
    tool_name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolCallRead(ToolCallRequest):
    tool_call_id: UUID = Field(default_factory=uuid4)
    status: ToolCallStatus = ToolCallStatus.REQUESTED
    result_summary: str | None = Field(default=None, max_length=12_000)
    error_code: str | None = Field(default=None, max_length=100)
    error_message: str | None = Field(default=None, max_length=2000)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)


class ToolCallResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_call_id: UUID
    tool_name: str
    status: ToolCallStatus
    content: dict[str, Any] | list[Any] | str | int | float | bool | None = None
    error_code: str | None = None
    error_message: str | None = None

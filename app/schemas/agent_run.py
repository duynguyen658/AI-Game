from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import AgentName, AgentRunStatus


class AgentRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: UUID
    campaign_id: str = Field(min_length=3, max_length=100)
    agent_name: AgentName
    model: str | None = Field(default=None, max_length=200)
    prompt_version: str = Field(min_length=1, max_length=50)


class AgentRunRead(AgentRunCreate):
    agent_run_id: UUID = Field(default_factory=uuid4)
    status: AgentRunStatus = AgentRunStatus.CREATED
    iteration_count: int = Field(default=0, ge=0)
    llm_call_count: int = Field(default=0, ge=0)
    tool_call_count: int = Field(default=0, ge=0)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    error_code: str | None = Field(default=None, max_length=100)
    error_message: str | None = Field(default=None, max_length=2000)


class AgentRunListItem(AgentRunRead):
    model_config = ConfigDict(extra="forbid", title="AgentRunListItem")


class AgentRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run: AgentRunRead
    output: dict[str, object] | None = None

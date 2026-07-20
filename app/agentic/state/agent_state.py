from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import AgentName, AgentRunStatus
from app.llm.agent_turn import AgentMessage


class AgentState(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    agent_run_id: UUID
    workflow_id: UUID
    campaign_id: str
    agent_name: AgentName
    status: AgentRunStatus = AgentRunStatus.CREATED
    iteration_count: int = Field(default=0, ge=0)
    llm_call_count: int = Field(default=0, ge=0)
    tool_call_count: int = Field(default=0, ge=0)
    messages: list[AgentMessage] = Field(default_factory=list)
    final_output: dict[str, Any] | None = None
    last_error_code: str | None = None

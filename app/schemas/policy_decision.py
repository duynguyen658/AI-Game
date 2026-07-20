from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import AgentName, CampaignStatus, PolicyDecision, UserRole


class PolicyEvaluationContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_run_id: UUID
    workflow_id: UUID
    campaign_id: str = Field(min_length=3, max_length=100)
    agent_name: AgentName
    action_name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)
    campaign_status: CampaignStatus
    workflow_status: CampaignStatus
    actor_id: str | None = Field(default=None, max_length=200)
    actor_role: UserRole | None = None
    revision_number: int = Field(default=0, ge=0)
    previous_action_count: int = Field(default=0, ge=0)


class PolicyEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: PolicyDecision
    reason_code: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=500)
    required_role: UserRole | None = None
    expires_in_seconds: int | None = Field(default=None, ge=60, le=86_400)
    reversible: bool

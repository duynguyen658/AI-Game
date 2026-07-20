from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.constants import (
    ActionRequestStatus,
    AgentName,
    PolicyDecision,
    UserRole,
)


class AgentActionProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action_name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)
    rationale_summary: str = Field(min_length=1, max_length=1000)


class ActionRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_run_id: UUID
    workflow_id: UUID
    campaign_id: str = Field(min_length=3, max_length=100)
    agent_name: AgentName
    action_name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)
    rationale_summary: str = Field(min_length=1, max_length=1000)
    idempotency_key: str = Field(min_length=64, max_length=64)


class ActionRequestRead(ActionRequestCreate):
    action_request_id: UUID
    policy_decision: PolicyDecision
    policy_reason_code: str = Field(max_length=100)
    policy_reason: str = Field(max_length=500)
    required_role: UserRole | None = None
    status: ActionRequestStatus
    requested_at: datetime
    expires_at: datetime | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    rejected_by: str | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class ActionApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class ActionRejectRequest(ActionApproveRequest):
    reason: str = Field(min_length=1, max_length=1000)


class ActionExecuteRequest(ActionApproveRequest):
    pass


class ActionProposalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_request: ActionRequestRead
    execution_status: str | None = None
    result_summary: str | None = Field(default=None, max_length=12_000)

    @model_validator(mode="after")
    def hide_result_before_completion(self) -> "ActionProposalResult":
        if (
            self.result_summary
            and self.action_request.status != ActionRequestStatus.COMPLETED
        ):
            raise ValueError("result summary requires completed action")
        return self

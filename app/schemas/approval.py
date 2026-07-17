from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.constants import (
    ApprovalDecision,
    UserRole,
)


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )
    campaign_id: str = Field(
        min_length=3,
        max_length=100,
    )
    workflow_id: UUID
    decision: ApprovalDecision
    feedback: str | None = Field(
        default=None,
        max_length=5000,
    )
    expected_version: int = Field(
        default=1,
        ge=1,
    )

    @model_validator(mode="after")
    def validate_feedback(self) -> ApprovalRequest:
        decisions_requiring_feedback = {
            ApprovalDecision.REJECT,
            ApprovalDecision.REQUEST_REVISION,
        }
        if self.decision in decisions_requiring_feedback and not self.feedback:
            raise ValueError(
                "feedback is required when rejecting or requesting revision"
            )
        return self


class ApprovalRecord(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )
    campaign_id: str = Field(
        min_length=3,
        max_length=100,
    )
    workflow_id: UUID
    decision: ApprovalDecision
    feedback: str | None = Field(
        default=None,
        max_length=5000,
    )
    actor_id: str = Field(
        min_length=1,
        max_length=200,
    )
    actor_role: UserRole
    previous_version: int = Field(
        ge=1,
    )
    resulting_version: int = Field(
        ge=1,
    )
    decided_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )

    @model_validator(mode="after")
    def validate_versions(self) -> ApprovalRecord:
        if self.resulting_version < self.previous_version:
            raise ValueError("resulting_version cannot be lower than previous_version")
        return self

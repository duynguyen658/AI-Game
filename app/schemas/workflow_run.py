from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.core.constants import CampaignStatus, WorkflowStep


class WorkflowRun(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    workflow_id: UUID = Field(default_factory=uuid4)

    campaign_id: str = Field(
        min_length=3,
        max_length=100,
    )

    status: CampaignStatus = CampaignStatus.RECEIVED

    current_step: WorkflowStep = WorkflowStep.RECEIVE_CAMPAIGN

    llm_call_count: int = Field(
        default=0,
        ge=0,
    )

    retry_count: int = Field(
        default=0,
        ge=0,
    )

    quality_score: int | None = Field(
        default=None,
        ge=0,
        le=100,
    )

    error_code: str | None = Field(
        default=None,
        max_length=100,
    )

    error_message: str | None = Field(
        default=None,
        max_length=2000,
    )

    started_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )

    completed_at: datetime | None = None

    @field_validator("started_at", "completed_at")
    @classmethod
    def require_timezone(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "datetime must include timezone information"
            )

        return value

    @model_validator(mode="after")
    def validate_timestamp_order(self) -> "WorkflowRun":
        if (
            self.completed_at is not None
            and self.completed_at < self.started_at
        ):
            raise ValueError(
                "completed_at cannot be earlier than started_at"
            )

        return self
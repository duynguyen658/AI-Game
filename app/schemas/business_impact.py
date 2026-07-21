from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AcceptanceFields(BaseModel):
    output_accepted: bool | None = None
    accepted_without_editing: bool = False
    editing_minutes: Decimal = Field(ge=0)
    rework_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_acceptance(self) -> AcceptanceFields:
        if self.accepted_without_editing:
            if self.output_accepted is not True:
                raise ValueError(
                    "accepted_without_editing requires explicit output acceptance"
                )
            if self.editing_minutes != 0 or self.rework_count != 0:
                raise ValueError(
                    "accepted_without_editing requires zero editing and rework"
                )
        return self


class TaskBaselineCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type: str = Field(min_length=1, max_length=100)
    department: str = Field(min_length=1, max_length=100)
    manual_duration_minutes: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    manual_steps: int = Field(ge=0, le=100_000)
    historical_error_rate: Decimal = Field(ge=0, le=1)
    baseline_cost: Decimal = Field(ge=0, max_digits=14, decimal_places=4)
    sample_size: int = Field(ge=1)
    source: str = Field(min_length=1, max_length=500)


class TaskBaselineRead(TaskBaselineCreate):
    task_baseline_id: UUID
    version: int
    created_by: str
    created_at: datetime
    updated_at: datetime


class TaskImpactCreate(AcceptanceFields):
    model_config = ConfigDict(extra="forbid")

    department: str | None = Field(default=None, max_length=100)
    manual_duration_baseline_override: Decimal | None = Field(default=None, ge=0)
    steps_before: int = Field(ge=0)
    automated_steps: int = Field(ge=0)
    error_count: int = Field(ge=0)


class TaskImpactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ai_task_impact_id: UUID
    task_run_id: UUID
    task_type: str
    department: str | None
    workflow_id: UUID | None
    job_id: UUID | None
    agent_run_id: UUID | None
    prompt_version_id: UUID | None
    provider: str
    model: str
    manual_duration_baseline: Decimal
    ai_duration_minutes: Decimal
    minutes_saved: Decimal
    steps_before: int
    steps_after: int
    automated_steps: int
    automation_rate: Decimal
    task_completed_successfully: bool
    output_accepted: bool | None
    accepted_without_editing: bool
    editing_minutes: Decimal
    rework_count: int
    error_count: int
    estimated_cost: Decimal
    created_at: datetime


class UserFeedbackCreate(AcceptanceFields):
    model_config = ConfigDict(extra="forbid")

    rating: int = Field(ge=1, le=5)
    helpfulness: int = Field(ge=1, le=5)
    accuracy: int = Field(ge=1, le=5)
    ease_of_use: int = Field(ge=1, le=5)
    would_use_again: bool
    comment: str | None = Field(default=None, max_length=2000)
    expected_version: int | None = Field(default=None, ge=1)


class UserFeedbackRead(UserFeedbackCreate):
    user_feedback_id: UUID
    task_run_id: UUID
    task_type: str
    workflow_id: UUID | None
    agent_run_id: UUID | None
    prompt_version_id: UUID | None
    provider: str
    model: str
    actor_id: str
    version: int
    created_at: datetime
    updated_at: datetime


class BusinessImpactAnalytics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    completed_tasks: int
    total_minutes_saved: Decimal
    average_automation_rate: Decimal
    technical_success_rate: Decimal
    human_acceptance_rate: Decimal
    first_pass_acceptance_rate: Decimal
    revision_rate: Decimal
    error_rate: Decimal
    user_satisfaction: Decimal
    would_use_again_rate: Decimal
    total_estimated_cost: Decimal
    series: list[dict[str, object]]

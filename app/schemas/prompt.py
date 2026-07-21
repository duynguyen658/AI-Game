from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import (
    ProviderName,
    PromptExperimentStatus,
    PromptTemplateStatus,
    PromptVersionStatus,
)


class PromptTemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120)
    agent_name: str | None = Field(default=None, max_length=50)
    task_type: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1000)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


class PromptVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_prompt: str = Field(min_length=1, max_length=30_000)
    user_prompt_template: str = Field(min_length=1, max_length=30_000)
    variables: dict[str, Any] = Field(default_factory=dict)
    change_summary: str = Field(min_length=1, max_length=1000)
    model_requirements: dict[str, Any] = Field(default_factory=dict)


class PromptTemplateRead(PromptTemplateCreate):
    prompt_template_id: UUID
    status: PromptTemplateStatus
    version: int
    created_by: str
    created_at: datetime
    updated_at: datetime


class PromptVersionRead(PromptVersionCreate):
    prompt_version_id: UUID
    prompt_template_id: UUID
    version: int
    status: PromptVersionStatus
    approved_by: str | None
    created_by: str
    created_at: datetime
    approved_at: datetime | None
    activated_at: datetime | None
    retired_at: datetime | None
    content_hash: str


class ExpectedVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_status: PromptVersionStatus


class PromptActivationRequest(ExpectedVersionRequest):
    expected_template_version: int = Field(ge=1)


class PromptRollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_version_id: UUID
    expected_template_version: int = Field(ge=1)


class PromptExperimentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_template_id: UUID
    control_version_id: UUID
    candidate_version_id: UUID
    evaluation_dataset_id: UUID
    provider: ProviderName
    model: str = Field(min_length=1, max_length=200)
    sample_size: int = Field(ge=1, le=10_000)
    execution_settings: dict[str, Any] = Field(default_factory=dict)


class PromptExperimentRun(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PromptExperimentRead(PromptExperimentCreate):
    experiment_id: UUID
    status: PromptExperimentStatus
    job_id: UUID | None
    dataset_version: str | None = None
    model_configuration_hash: str | None = None
    tool_registry_version: str | None = None
    policy_version: str | None = None
    application_version: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_by: str
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    result: dict[str, Any] | None = None


class PromptExperimentCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    case_result_id: UUID
    evaluation_case_id: UUID
    prompt_version_id: UUID
    variant: str
    status: str
    output: dict[str, Any] | None
    metrics: dict[str, Any]
    error_code: str | None
    error_message: str | None
    created_at: datetime

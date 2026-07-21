from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import EvaluationResultStatus, EvaluationRunStatus


class EvaluationCaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    campaign_input: dict[str, Any]
    actual_output: dict[str, Any]
    expected: dict[str, Any]
    thresholds: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class EvaluationDatasetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    cases: list[EvaluationCaseCreate] = Field(min_length=1, max_length=100)


class EvaluationDatasetRead(BaseModel):
    dataset_id: UUID
    name: str
    version: str
    description: str | None
    case_count: int
    created_by: str
    created_at: datetime


class EvaluationResultRead(BaseModel):
    evaluation_result_id: UUID
    evaluation_case_id: UUID
    case_name: str
    status: EvaluationResultStatus
    assertions: dict[str, Any]
    metrics: dict[str, Any]
    output_summary: str | None
    duration_ms: int
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    error_code: str | None
    error_message: str | None


class EvaluationRunRead(BaseModel):
    evaluation_run_id: UUID
    dataset_id: UUID
    status: EvaluationRunStatus
    dataset_version: str
    model_name: str
    model_configuration_hash: str
    prompt_version: str
    tool_registry_version: str
    policy_version: str
    application_version: str
    total_cases: int
    completed_cases: int
    metrics: dict[str, Any]
    regression_passed: bool | None
    correlation_id: str
    created_by: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_code: str | None
    error_message: str | None
    results: list[EvaluationResultRead] = Field(default_factory=list)


class EvaluationRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: UUID

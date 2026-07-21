from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import ProviderName


class ProviderCatalogItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: ProviderName
    configured: bool
    capabilities: dict[str, Any]


class ProviderComparisonCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_version_id: UUID
    dataset_id: UUID
    providers: list[ProviderName] = Field(min_length=2, max_length=3)
    model_by_provider: dict[ProviderName, str]
    sample_size: int = Field(default=100, ge=1, le=10_000)
    execution_settings: dict[str, Any] = Field(default_factory=dict)


class ProviderComparisonRun(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderComparisonRead(ProviderComparisonCreate):
    comparison_id: UUID
    status: str
    report: dict[str, Any] | None
    job_id: UUID | None
    dataset_version: str | None
    created_by: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_code: str | None
    error_message: str | None


class ProviderComparisonCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    case_result_id: UUID
    evaluation_case_id: UUID
    provider: ProviderName
    model: str
    status: str
    output: dict[str, Any] | None
    metrics: dict[str, Any]
    error_code: str | None
    error_message: str | None
    created_at: datetime

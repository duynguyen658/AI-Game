from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import ProviderName


class ProviderCatalogItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: ProviderName
    configured: bool
    capabilities: dict[str, Any]


class ProviderComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_version_id: UUID
    dataset_id: UUID
    providers: list[ProviderName] = Field(min_length=2, max_length=3)
    model_by_provider: dict[ProviderName, str]
    fixture_metrics: dict[ProviderName, dict[str, float]] | None = None


class ProviderComparisonReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_version_id: UUID
    dataset_id: UUID
    comparisons: list[dict[str, Any]]
    recommended_provider: ProviderName | None
    human_decision_required: bool = True

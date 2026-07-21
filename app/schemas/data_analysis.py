from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class DataQualityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_count: int
    column_count: int
    columns: list[str]
    missing_value_rate: str
    duplicate_row_count: int
    unsupported_columns: list[str]
    preview: list[dict[str, str]]


class DataAnalysisReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_quality: DataQualityReport
    summary_metrics: dict[str, str | int | None]
    segment_performance: list[dict[str, Any]]
    anomalies: list[dict[str, Any]]
    trends: list[dict[str, Any]]
    explanation: str
    recommendations: list[str]
    limitations: list[str]
    generated_at: datetime

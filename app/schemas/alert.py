from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.constants import AlertStatus, AlertType, SecuritySeverity


class AlertRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alert_id: UUID
    alert_type: AlertType
    status: AlertStatus
    severity: SecuritySeverity
    resource_type: str
    resource_id: str
    summary: str
    details: dict[str, Any]
    first_seen_at: datetime
    last_seen_at: datetime
    acknowledged_by: str | None
    acknowledged_at: datetime | None
    resolved_by: str | None
    resolved_at: datetime | None
    occurrence_count: int
    correlation_id: str

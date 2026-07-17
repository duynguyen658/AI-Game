from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from app.core.constants import (
    SecurityEventType,
    SecuritySeverity,
)


class SecurityEvent(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )
    event_id: UUID = Field(
        default_factory=uuid4,
    )
    event_type: SecurityEventType
    severity: SecuritySeverity
    campaign_id: str | None = Field(
        default=None,
        max_length=100,
    )
    workflow_id: UUID | None = None
    actor_id: str | None = Field(
        default=None,
        max_length=200,
    )
    source: str = Field(
        min_length=1,
        max_length=100,
    )
    message: str = Field(
        min_length=1,
        max_length=1000,
    )
    metadata: dict[str, JsonValue] = Field(
        default_factory=dict,
    )
    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )

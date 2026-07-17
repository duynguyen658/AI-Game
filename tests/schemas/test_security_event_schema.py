import pytest
from pydantic import ValidationError

from app.core.constants import (
    SecurityEventType,
    SecuritySeverity,
)
from app.schemas.security_event import SecurityEvent


def test_security_event_uses_default_values() -> None:
    event = SecurityEvent(
        event_type=SecurityEventType.PROMPT_INJECTION_DETECTED,
        severity=SecuritySeverity.HIGH,
        source="campaign_input",
        message="Suspicious input detected.",
    )

    assert event.event_id is not None
    assert event.occurred_at.tzinfo is not None
    assert event.metadata == {}


def test_security_event_rejects_unknown_field() -> None:
    with pytest.raises(
        ValidationError,
        match="Extra inputs are not permitted",
    ):
        SecurityEvent(
            event_type=SecurityEventType.UNAUTHORIZED_ACCESS,
            severity=SecuritySeverity.HIGH,
            source="approval_api",
            message="Unauthorized approval attempt.",
            api_key="must-not-be-accepted",
        )

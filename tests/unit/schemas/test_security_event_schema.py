import pytest
from pydantic import ValidationError

from app.core.constants import SecurityEventType, SecuritySeverity
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


def test_security_event_accepts_json_metadata() -> None:
    event = SecurityEvent(
        event_type=SecurityEventType.RATE_LIMIT_EXCEEDED,
        severity=SecuritySeverity.MEDIUM,
        source="campaign_api",
        message="Rate limit exceeded.",
        metadata={
            "blocked": True,
            "request_count": 21,
            "tags": ["rate-limit", "api"],
        },
    )

    assert event.metadata["blocked"] is True
    assert event.metadata["request_count"] == 21


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


def test_security_event_rejects_empty_source() -> None:
    with pytest.raises(ValidationError):
        SecurityEvent(
            event_type=SecurityEventType.UNAUTHORIZED_ACCESS,
            severity=SecuritySeverity.HIGH,
            source="",
            message="Unauthorized approval attempt.",
        )


def test_security_event_rejects_non_json_metadata() -> None:
    with pytest.raises(ValidationError):
        SecurityEvent(
            event_type=SecurityEventType.SENSITIVE_DATA_DETECTED,
            severity=SecuritySeverity.HIGH,
            source="campaign_input",
            message="Sensitive data detected.",
            metadata={"invalid": {1, 2, 3}},
        )

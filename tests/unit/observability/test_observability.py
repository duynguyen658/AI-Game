from uuid import UUID

from app.observability.logging import redact_log_event
from app.observability.middleware import valid_or_new_correlation_id


def test_correlation_id_is_propagated_or_replaced() -> None:
    expected = "6a6e1b0d-596f-49e8-8381-72fb1e036adb"
    assert valid_or_new_correlation_id(expected) == expected
    assert valid_or_new_correlation_id("not-a-uuid") != "not-a-uuid"
    UUID(valid_or_new_correlation_id(None))


def test_structured_log_redaction_is_recursive() -> None:
    event = redact_log_event(
        None,
        "info",
        {
            "event": "test",
            "authorization": "Bearer abc.def",
            "nested": {"api_key": "sk-test", "safe": "ok"},
            "message": "password=super-secret",
        },
    )
    assert event["authorization"] == "[REDACTED]"
    assert event["nested"]["api_key"] == "[REDACTED]"
    assert event["nested"]["safe"] == "ok"
    assert "super-secret" not in event["message"]

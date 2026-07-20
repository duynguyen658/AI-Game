from sqlalchemy.exc import IntegrityError

from app.database.m5_integrity import (
    is_action_execution_duplicate,
    is_action_request_duplicate,
    is_memory_execution_event_duplicate,
)


def integrity_error(constraint_name: str | None) -> IntegrityError:
    diagnostic = type("Diagnostic", (), {"constraint_name": constraint_name})()
    original = type("Original", (), {"diag": diagnostic})()
    return IntegrityError("insert", {}, original)


def test_maps_only_known_m5_duplicate_constraints() -> None:
    assert is_action_request_duplicate(
        integrity_error("uq_action_requests_idempotency_key")
    )
    assert is_action_execution_duplicate(
        integrity_error("uq_action_executions_one_per_request")
    )
    assert is_action_execution_duplicate(
        integrity_error("uq_action_executions_idempotency_key")
    )
    assert is_memory_execution_event_duplicate(
        integrity_error("uq_memory_entries_execution_event")
    )


def test_unknown_or_missing_constraint_is_not_mapped_as_duplicate() -> None:
    unknown = integrity_error("fk_action_executions_request")
    missing = integrity_error(None)

    for error in (unknown, missing):
        assert not is_action_request_duplicate(error)
        assert not is_action_execution_duplicate(error)
        assert not is_memory_execution_event_duplicate(error)

from sqlalchemy.exc import IntegrityError

from app.database.integrity import get_constraint_name

ACTION_REQUEST_IDEMPOTENCY_CONSTRAINT = "uq_action_requests_idempotency_key"
ACTION_EXECUTION_CONSTRAINTS = frozenset(
    {
        "uq_action_executions_one_per_request",
        "uq_action_executions_idempotency_key",
    }
)
MEMORY_EXECUTION_EVENT_CONSTRAINT = "uq_memory_entries_execution_event"


def is_action_request_duplicate(exc: IntegrityError) -> bool:
    return get_constraint_name(exc) == ACTION_REQUEST_IDEMPOTENCY_CONSTRAINT


def is_action_execution_duplicate(exc: IntegrityError) -> bool:
    return get_constraint_name(exc) in ACTION_EXECUTION_CONSTRAINTS


def is_memory_execution_event_duplicate(exc: IntegrityError) -> bool:
    return get_constraint_name(exc) == MEMORY_EXECUTION_EVENT_CONSTRAINT

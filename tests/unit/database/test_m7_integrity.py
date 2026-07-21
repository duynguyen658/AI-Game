from types import SimpleNamespace

from sqlalchemy.exc import IntegrityError

from app.database.m7_integrity import (
    IMPACT_TASK_UNIQUE_CONSTRAINT,
    MEDIA_ATTEMPT_NUMBER_CONSTRAINT,
    MEDIA_IDEMPOTENCY_CONSTRAINT,
    is_constraint,
    is_media_request_idempotency_conflict,
)


def integrity_error(constraint_name: str | None) -> IntegrityError:
    original = Exception("database failure")
    original.diag = SimpleNamespace(constraint_name=constraint_name)  # type: ignore[attr-defined]
    return IntegrityError("insert", {}, original)


def test_m7_integrity_maps_only_known_constraints() -> None:
    assert is_constraint(
        integrity_error(IMPACT_TASK_UNIQUE_CONSTRAINT),
        IMPACT_TASK_UNIQUE_CONSTRAINT,
    )
    assert is_constraint(
        integrity_error(MEDIA_ATTEMPT_NUMBER_CONSTRAINT),
        MEDIA_ATTEMPT_NUMBER_CONSTRAINT,
    )
    assert is_media_request_idempotency_conflict(
        integrity_error(MEDIA_IDEMPOTENCY_CONSTRAINT)
    )


def test_m7_integrity_does_not_map_unknown_fk_check_or_null_constraints() -> None:
    for constraint in (
        "uq_unknown_constraint",
        "fk_media_attempts_job_id",
        "ck_media_attempt_status",
        None,
    ):
        error = integrity_error(constraint)
        assert not is_constraint(error, IMPACT_TASK_UNIQUE_CONSTRAINT)
        assert not is_media_request_idempotency_conflict(error)

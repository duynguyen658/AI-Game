from sqlalchemy.exc import IntegrityError

from app.database.integrity import get_constraint_name

IMPACT_TASK_UNIQUE_CONSTRAINT = "uq_ai_task_impacts_task_run"
FEEDBACK_TASK_ACTOR_UNIQUE_CONSTRAINT = "uq_user_feedback_task_actor"
MEDIA_IDEMPOTENCY_CONSTRAINT = "uq_media_assets_actor_idempotency"
MEDIA_JOB_IDEMPOTENCY_CONSTRAINT = "uq_background_jobs_idempotency"
MEDIA_ATTEMPT_NUMBER_CONSTRAINT = "uq_media_attempt_number"
PROMPT_TEMPLATE_SLUG_CONSTRAINT = "uq_prompt_templates_slug"

MEDIA_REQUEST_IDEMPOTENCY_CONSTRAINTS = frozenset(
    {MEDIA_IDEMPOTENCY_CONSTRAINT, MEDIA_JOB_IDEMPOTENCY_CONSTRAINT}
)


def is_constraint(exc: IntegrityError, expected: str) -> bool:
    return get_constraint_name(exc) == expected


def is_media_request_idempotency_conflict(exc: IntegrityError) -> bool:
    return get_constraint_name(exc) in MEDIA_REQUEST_IDEMPOTENCY_CONSTRAINTS

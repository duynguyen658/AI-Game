from app.core.constants import CampaignStatus
from app.core.exceptions import InvalidStateTransitionError


ALLOWED_TRANSITIONS: dict[
    CampaignStatus,
    frozenset[CampaignStatus],
] = {
    CampaignStatus.RECEIVED: frozenset(
        {
            CampaignStatus.VALIDATING,
            CampaignStatus.FAILED,
        }
    ),
    CampaignStatus.VALIDATING: frozenset(
        {
            CampaignStatus.ANALYZING,
            CampaignStatus.NEEDS_CLARIFICATION,
            CampaignStatus.FAILED,
        }
    ),
    CampaignStatus.ANALYZING: frozenset(
        {
            CampaignStatus.GENERATING,
            CampaignStatus.NEEDS_CLARIFICATION,
            CampaignStatus.FAILED,
        }
    ),
    CampaignStatus.GENERATING: frozenset(
        {
            CampaignStatus.REVIEWING,
            CampaignStatus.FAILED,
        }
    ),
    CampaignStatus.REVIEWING: frozenset(
        {
            CampaignStatus.GENERATING,
            CampaignStatus.MANUAL_REVIEW_REQUIRED,
            CampaignStatus.PENDING_APPROVAL,
            CampaignStatus.FAILED,
        }
    ),
    CampaignStatus.MANUAL_REVIEW_REQUIRED: frozenset(
        {
            CampaignStatus.PENDING_APPROVAL,
            CampaignStatus.REVISION_REQUIRED,
            CampaignStatus.REJECTED,
        }
    ),
    CampaignStatus.PENDING_APPROVAL: frozenset(
        {
            CampaignStatus.APPROVED,
            CampaignStatus.REJECTED,
            CampaignStatus.REVISION_REQUIRED,
        }
    ),
    CampaignStatus.REVISION_REQUIRED: frozenset(
        {
            CampaignStatus.GENERATING,
            CampaignStatus.REJECTED,
        }
    ),
    CampaignStatus.NEEDS_CLARIFICATION: frozenset(
        {
            CampaignStatus.VALIDATING,
            CampaignStatus.REJECTED,
        }
    ),
    CampaignStatus.APPROVED: frozenset(),
    CampaignStatus.REJECTED: frozenset(),
    CampaignStatus.FAILED: frozenset(),
}


def get_allowed_transitions(
    current_status: CampaignStatus,
) -> frozenset[CampaignStatus]:
    return ALLOWED_TRANSITIONS[current_status]


def can_transition(
    current_status: CampaignStatus,
    next_status: CampaignStatus,
) -> bool:
    return next_status in get_allowed_transitions(current_status)


def ensure_valid_transition(
    current_status: CampaignStatus,
    next_status: CampaignStatus,
) -> None:
    if can_transition(current_status, next_status):
        return

    raise InvalidStateTransitionError(
        f"Cannot transition from {current_status.value} to {next_status.value}."
    )

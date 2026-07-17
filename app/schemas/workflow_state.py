from app.core.constants import CampaignStatus
from app.core.exceptions import InvalidStateTransitionError


ALLOWED_TRANSITIONS: dict[CampaignStatus, set[CampaignStatus]] = {
    CampaignStatus.RECEIVED: {
        CampaignStatus.VALIDATING,
        CampaignStatus.FAILED,
    },
    CampaignStatus.VALIDATING: {
        CampaignStatus.ANALYZING,
        CampaignStatus.NEEDS_CLARIFICATION,
        CampaignStatus.FAILED,
    },
    CampaignStatus.ANALYZING: {
        CampaignStatus.GENERATING,
        CampaignStatus.NEEDS_CLARIFICATION,
        CampaignStatus.FAILED,
    },
    CampaignStatus.GENERATING: {
        CampaignStatus.REVIEWING,
        CampaignStatus.FAILED,
    },
    CampaignStatus.REVIEWING: {
        CampaignStatus.GENERATING,
        CampaignStatus.PENDING_APPROVAL,
        CampaignStatus.FAILED,
    },
    CampaignStatus.PENDING_APPROVAL: {
        CampaignStatus.APPROVED,
        CampaignStatus.REJECTED,
        CampaignStatus.REVISION_REQUIRED,
    },
    CampaignStatus.REVISION_REQUIRED: {
        CampaignStatus.GENERATING,
        CampaignStatus.REJECTED,
    },
    CampaignStatus.NEEDS_CLARIFICATION: {
        CampaignStatus.VALIDATING,
        CampaignStatus.REJECTED,
    },
    CampaignStatus.APPROVED: set(),
    CampaignStatus.REJECTED: set(),
    CampaignStatus.FAILED: set(),
}


def ensure_valid_transition(
    current_status: CampaignStatus,
    next_status: CampaignStatus,
) -> None:
    allowed = ALLOWED_TRANSITIONS.get(current_status, set())

    if next_status not in allowed:
        raise InvalidStateTransitionError(
            f"Cannot transition from {current_status} to {next_status}."
        )
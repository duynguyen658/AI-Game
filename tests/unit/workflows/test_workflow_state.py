import pytest

from app.core.constants import CampaignStatus
from app.core.exceptions import InvalidStateTransitionError
from app.workflows.workflow_state import (
    ALLOWED_TRANSITIONS,
    can_transition,
    ensure_valid_transition,
    get_allowed_transitions,
)


@pytest.mark.parametrize(
    ("current_status", "next_status"),
    [
        (CampaignStatus.RECEIVED, CampaignStatus.VALIDATING),
        (CampaignStatus.VALIDATING, CampaignStatus.ANALYZING),
        (CampaignStatus.VALIDATING, CampaignStatus.NEEDS_CLARIFICATION),
        (CampaignStatus.ANALYZING, CampaignStatus.GENERATING),
        (CampaignStatus.GENERATING, CampaignStatus.REVIEWING),
        (CampaignStatus.REVIEWING, CampaignStatus.GENERATING),
        (
            CampaignStatus.REVIEWING,
            CampaignStatus.MANUAL_REVIEW_REQUIRED,
        ),
        (
            CampaignStatus.REVIEWING,
            CampaignStatus.PENDING_APPROVAL,
        ),
        (
            CampaignStatus.MANUAL_REVIEW_REQUIRED,
            CampaignStatus.PENDING_APPROVAL,
        ),
        (
            CampaignStatus.PENDING_APPROVAL,
            CampaignStatus.APPROVED,
        ),
        (
            CampaignStatus.PENDING_APPROVAL,
            CampaignStatus.REVISION_REQUIRED,
        ),
        (
            CampaignStatus.REVISION_REQUIRED,
            CampaignStatus.GENERATING,
        ),
    ],
)
def test_valid_transitions(
    current_status: CampaignStatus,
    next_status: CampaignStatus,
) -> None:
    assert can_transition(current_status, next_status) is True
    ensure_valid_transition(current_status, next_status)


@pytest.mark.parametrize(
    ("current_status", "next_status"),
    [
        (CampaignStatus.RECEIVED, CampaignStatus.APPROVED),
        (CampaignStatus.ANALYZING, CampaignStatus.APPROVED),
        (CampaignStatus.APPROVED, CampaignStatus.GENERATING),
        (CampaignStatus.REJECTED, CampaignStatus.APPROVED),
        (CampaignStatus.FAILED, CampaignStatus.RECEIVED),
    ],
)
def test_invalid_transitions(
    current_status: CampaignStatus,
    next_status: CampaignStatus,
) -> None:
    assert can_transition(current_status, next_status) is False

    with pytest.raises(InvalidStateTransitionError):
        ensure_valid_transition(current_status, next_status)


@pytest.mark.parametrize(
    "terminal_status",
    [
        CampaignStatus.APPROVED,
        CampaignStatus.REJECTED,
        CampaignStatus.FAILED,
    ],
)
def test_terminal_statuses_have_no_next_state(
    terminal_status: CampaignStatus,
) -> None:
    assert get_allowed_transitions(terminal_status) == frozenset()


def test_all_campaign_statuses_are_registered() -> None:
    assert set(ALLOWED_TRANSITIONS) == set(CampaignStatus)

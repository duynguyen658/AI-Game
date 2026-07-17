from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.constants import ApprovalDecision, UserRole
from app.schemas.approval import ApprovalRecord, ApprovalRequest


def test_approve_does_not_require_feedback() -> None:
    request = ApprovalRequest(
        campaign_id="CL-PREREG-001",
        workflow_id=uuid4(),
        decision=ApprovalDecision.APPROVE,
        expected_version=1,
    )

    assert request.feedback is None


@pytest.mark.parametrize(
    "decision",
    [
        ApprovalDecision.REJECT,
        ApprovalDecision.REQUEST_REVISION,
    ],
)
def test_negative_decision_requires_feedback(
    decision: ApprovalDecision,
) -> None:
    with pytest.raises(
        ValidationError,
        match="feedback is required",
    ):
        ApprovalRequest(
            campaign_id="CL-PREREG-001",
            workflow_id=uuid4(),
            decision=decision,
            expected_version=1,
        )


def test_whitespace_only_feedback_is_rejected() -> None:
    with pytest.raises(
        ValidationError,
        match="feedback is required",
    ):
        ApprovalRequest(
            campaign_id="CL-PREREG-001",
            workflow_id=uuid4(),
            decision=ApprovalDecision.REJECT,
            feedback="   ",
            expected_version=1,
        )


def test_expected_version_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        ApprovalRequest(
            campaign_id="CL-PREREG-001",
            workflow_id=uuid4(),
            decision=ApprovalDecision.APPROVE,
            expected_version=0,
        )


def test_approval_request_rejects_unknown_field() -> None:
    with pytest.raises(
        ValidationError,
        match="Extra inputs are not permitted",
    ):
        ApprovalRequest(
            campaign_id="CL-PREREG-001",
            workflow_id=uuid4(),
            decision=ApprovalDecision.APPROVE,
            expected_version=1,
            actor_role="admin",
        )


def test_approval_record_accepts_same_version() -> None:
    record = ApprovalRecord(
        campaign_id="CL-PREREG-001",
        workflow_id=uuid4(),
        decision=ApprovalDecision.APPROVE,
        actor_id="manager-01",
        actor_role=UserRole.MANAGER,
        previous_version=1,
        resulting_version=1,
    )

    assert record.resulting_version == 1
    assert record.decided_at.tzinfo is not None


def test_approval_record_rejects_version_regression() -> None:
    with pytest.raises(
        ValidationError,
        match="resulting_version cannot be lower",
    ):
        ApprovalRecord(
            campaign_id="CL-PREREG-001",
            workflow_id=uuid4(),
            decision=ApprovalDecision.REQUEST_REVISION,
            feedback="Please revise the Facebook content.",
            actor_id="manager-01",
            actor_role=UserRole.MANAGER,
            previous_version=2,
            resulting_version=1,
        )

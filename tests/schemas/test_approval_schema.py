from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.constants import ApprovalDecision
from app.schemas.approval import ApprovalRequest


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


def test_negative_decision_accepts_feedback() -> None:
    request = ApprovalRequest(
        campaign_id="CL-PREREG-001",
        workflow_id=uuid4(),
        decision=ApprovalDecision.REJECT,
        feedback="Campaign contains incorrect promotion.",
        expected_version=1,
    )

    assert request.feedback == ("Campaign contains incorrect promotion.")

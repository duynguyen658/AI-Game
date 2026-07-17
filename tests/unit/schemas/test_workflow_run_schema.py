from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.core.constants import CampaignStatus, WorkflowStep
from app.schemas.workflow_run import WorkflowRun


def test_workflow_run_uses_defaults() -> None:
    workflow = WorkflowRun(campaign_id="CL-PREREG-001")

    assert workflow.workflow_id is not None
    assert workflow.status == CampaignStatus.RECEIVED
    assert workflow.current_step == WorkflowStep.RECEIVE_CAMPAIGN
    assert workflow.llm_call_count == 0
    assert workflow.retry_count == 0
    assert workflow.quality_score is None
    assert workflow.started_at.tzinfo is not None
    assert workflow.completed_at is None


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("llm_call_count", -1),
        ("retry_count", -1),
        ("quality_score", -1),
        ("quality_score", 101),
    ],
)
def test_workflow_run_rejects_invalid_numeric_values(
    field_name: str,
    invalid_value: int,
) -> None:
    payload = {
        "campaign_id": "CL-PREREG-001",
        field_name: invalid_value,
    }

    with pytest.raises(ValidationError):
        WorkflowRun.model_validate(payload)


def test_workflow_run_rejects_naive_started_at() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        WorkflowRun(
            campaign_id="CL-PREREG-001",
            started_at=datetime.now(),
        )


def test_workflow_run_rejects_completed_before_started() -> None:
    started_at = datetime.now(UTC)

    with pytest.raises(
        ValidationError,
        match="completed_at cannot be earlier",
    ):
        WorkflowRun(
            campaign_id="CL-PREREG-001",
            started_at=started_at,
            completed_at=started_at - timedelta(seconds=1),
        )


def test_workflow_run_rejects_unknown_field() -> None:
    with pytest.raises(
        ValidationError,
        match="Extra inputs are not permitted",
    ):
        WorkflowRun(
            campaign_id="CL-PREREG-001",
            unexpected_field="value",
        )


def test_workflow_run_validates_assignment() -> None:
    workflow = WorkflowRun(campaign_id="CL-PREREG-001")

    with pytest.raises(ValidationError):
        workflow.retry_count = -1

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.constants import CampaignStatus, WorkflowStep
from app.llm.mock_client import MockLLMClient
from app.workflows.campaign_workflow import CampaignWorkflow


@pytest.mark.asyncio
async def test_load_snapshot_uses_plain_reads_without_row_locks() -> None:
    workflow_id = uuid4()
    workflow_repo = SimpleNamespace(
        get_by_id=AsyncMock(
            return_value=SimpleNamespace(
                workflow_id=workflow_id,
                campaign_id="CL-SNAPSHOT",
                parent_workflow_id=None,
                revision_number=0,
                status=CampaignStatus.ANALYZING.value,
                current_step=WorkflowStep.ANALYZE_BRIEF.value,
                llm_call_count=1,
                retry_count=0,
                quality_score=None,
                error_code=None,
                error_message=None,
                started_at=datetime.now(UTC),
                completed_at=None,
            )
        ),
        get_by_id_for_update=AsyncMock(),
    )
    campaign_repo = SimpleNamespace(
        get_by_id=AsyncMock(
            return_value=SimpleNamespace(
                campaign_id="CL-SNAPSHOT",
                campaign_objective="Drive pre-registration",
                raw_brief="Launch campaign",
                brief_analysis=None,
                generated_content=None,
            )
        ),
        get_by_id_for_update=AsyncMock(),
    )
    session = SimpleNamespace(
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    workflow = CampaignWorkflow(session, MockLLMClient())
    workflow.workflow_repository = workflow_repo
    workflow.campaign_repository = campaign_repo

    snapshot = await workflow._load_snapshot(workflow_id)

    assert snapshot.workflow.workflow_id == workflow_id
    workflow_repo.get_by_id.assert_awaited_once_with(workflow_id)
    workflow_repo.get_by_id_for_update.assert_not_called()
    campaign_repo.get_by_id.assert_awaited_once_with("CL-SNAPSHOT")
    campaign_repo.get_by_id_for_update.assert_not_called()
    session.commit.assert_awaited_once()

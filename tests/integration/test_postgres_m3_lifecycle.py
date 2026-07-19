from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import date

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ApprovalDecision, CampaignStatus, UserRole
from app.core.exceptions import (
    LLMProviderError,
    VersionConflictError,
    WorkflowCreationNotAllowedError,
)
from app.database.session import AsyncSessionLocal
from app.llm.mock_client import MockLLMClient
from app.repositories.approval_repository import ApprovalRepository
from app.repositories.campaign_repository import CampaignRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.schemas.approval import ApprovalRequest
from app.schemas.approval import ApprovalRecord
from app.schemas.campaign import (
    BriefAnalysis,
    CampaignCreate,
    DiscordContent,
    FacebookContent,
    GeneratedContent,
    QualityReview,
    TikTokContent,
    TikTokScene,
)
from app.service.approval_service import ApprovalService
from app.service.workflow_service import WorkflowService
from app.workflows.campaign_workflow import CampaignWorkflow

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_TESTS") != "1",
        reason="set RUN_POSTGRES_TESTS=1 to run PostgreSQL integration tests",
    ),
]


@pytest_asyncio.fixture(autouse=True)
async def clean_database() -> AsyncIterator[None]:
    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                "TRUNCATE approval_records, workflow_runs, campaigns, security_events "
                "RESTART IDENTITY CASCADE"
            )
        )
        await session.commit()
    yield
    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                "TRUNCATE approval_records, workflow_runs, campaigns, security_events "
                "RESTART IDENTITY CASCADE"
            )
        )
        await session.commit()


def campaign_payload(campaign_id: str = "CL-M3-001") -> dict[str, object]:
    return {
        "campaign_id": campaign_id,
        "game_name": "Cyber Legends",
        "genre": "Action RPG",
        "target_audience": "18-30",
        "market": "Vietnam",
        "platforms": ["Facebook", "TikTok"],
        "campaign_objective": "Drive pre-registration",
        "tone": "Cyberpunk action",
        "launch_date": "2026-08-15",
        "promotion": "Limited hero and 500 gems",
        "raw_brief": "Pre-registration campaign",
    }


async def create_campaign(
    session: AsyncSession,
    campaign_id: str = "CL-M3-001",
) -> None:
    await CampaignRepository(session).create(
        CampaignCreate(
            campaign_id=campaign_id,
            game_name="Cyber Legends",
            genre="Action RPG",
            target_audience="18-30",
            market="Vietnam",
            platforms=["Facebook", "TikTok"],
            campaign_objective="Drive pre-registration",
            tone="Cyberpunk action",
            launch_date=date(2026, 8, 15),
            promotion="Limited hero and 500 gems",
            raw_brief="Pre-registration campaign",
        )
    )
    await session.commit()


def generated_content(title: str = "Cyber Legends") -> GeneratedContent:
    return GeneratedContent(
        facebook=FacebookContent(
            headline=f"{title} pre-registration",
            content="Reserve your rewards.",
            cta="Join now",
        ),
        tiktok=TikTokContent(
            hook="Enter the neon fight.",
            scenes=[
                TikTokScene(
                    order=1,
                    duration_seconds=3,
                    visual="Neon skyline",
                )
            ],
            voiceover="Pre-register today.",
            cta="Join now",
        ),
        discord=DiscordContent(
            title=f"{title} is live",
            message="Pre-registration rewards are waiting.",
            cta="Join now",
        ),
    )


def review(status: str, score: int = 88) -> QualityReview:
    return QualityReview(
        status=status,
        quality_score=score,
        factual_accuracy_score=score,
        tone_score=score,
        platform_fit_score=score,
    )


@pytest.mark.asyncio
async def test_workflow_retry_then_pass_persists_counters() -> None:
    async with AsyncSessionLocal() as session:
        await create_campaign(session)
        workflow = await WorkflowService(session).create_workflow("CL-M3-001")
        client = MockLLMClient(
            scripted_outputs=[
                BriefAnalysis(
                    summary="Campaign summary",
                    campaign_objective="Drive pre-registration",
                    target_audience="18-30",
                    main_message="Register now",
                ),
                generated_content("v1"),
                review("FAIL", 45),
                generated_content("v2"),
                review("PASS", 90),
            ]
        )

        result = await CampaignWorkflow(session, client).run_to_pending_approval(
            workflow.workflow_id
        )

        assert result.status == CampaignStatus.PENDING_APPROVAL
        assert result.retry_count == 1
        assert result.llm_call_count == 5
        assert client.call_count == 5


@pytest.mark.asyncio
async def test_postgres_rejects_duplicate_active_workflow_and_approval() -> None:
    async with AsyncSessionLocal() as session:
        await create_campaign(session)
        workflow_repo = WorkflowRepository(session)
        workflow = await workflow_repo.create("CL-M3-001")
        workflow_id = workflow.workflow_id
        await session.commit()
        with pytest.raises(IntegrityError):
            await workflow_repo.create("CL-M3-001")
        await session.rollback()

        approval_repo = ApprovalRepository(session)
        await approval_repo.create(
            ApprovalRecord(
                campaign_id="CL-M3-001",
                workflow_id=workflow_id,
                decision=ApprovalDecision.APPROVE,
                actor_id="manager-1",
                actor_role=UserRole.MANAGER,
                previous_version=1,
                resulting_version=1,
            )
        )
        with pytest.raises(IntegrityError):
            await approval_repo.create(
                ApprovalRecord(
                    campaign_id="CL-M3-001",
                    workflow_id=workflow_id,
                    decision=ApprovalDecision.REJECT,
                    feedback="No",
                    actor_id="manager-2",
                    actor_role=UserRole.MANAGER,
                    previous_version=1,
                    resulting_version=1,
                )
            )


@pytest.mark.asyncio
async def test_version_conflict_does_not_mark_failed() -> None:
    async with AsyncSessionLocal() as session:
        await create_campaign(session)
        workflow = await WorkflowService(session).create_workflow("CL-M3-001")
        await WorkflowService(session).transition(
            workflow.workflow_id,
            CampaignStatus.VALIDATING,
        )

        with pytest.raises(VersionConflictError):
            await CampaignWorkflow(session, MockLLMClient())._transition_checkpoint(
                workflow.workflow_id,
                expected_status=CampaignStatus.RECEIVED,
                next_status=CampaignStatus.VALIDATING,
                next_step=workflow.current_step,
            )

        persisted = await WorkflowRepository(session).get_by_id(workflow.workflow_id)
        assert persisted is not None
        assert persisted.status == CampaignStatus.VALIDATING.value
        assert persisted.error_code is None


@pytest.mark.asyncio
async def test_provider_failure_persists_failed_and_redacts_secret() -> None:
    async with AsyncSessionLocal() as session:
        await create_campaign(session)
        workflow = await WorkflowService(session).create_workflow("CL-M3-001")
        client = MockLLMClient(
            scripted_outputs=[
                LLMProviderError("password=super-secret Bearer abc.def.ghi")
            ]
        )

        with pytest.raises(LLMProviderError):
            await CampaignWorkflow(session, client).run_to_pending_approval(
                workflow.workflow_id
            )

        persisted = await WorkflowRepository(session).get_by_id(workflow.workflow_id)
        assert persisted is not None
        assert persisted.status == CampaignStatus.FAILED.value
        assert persisted.error_code == LLMProviderError.error_code
        assert "super-secret" not in (persisted.error_message or "")
        assert "abc.def.ghi" not in (persisted.error_message or "")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "blocked_status",
    [
        CampaignStatus.APPROVED,
        CampaignStatus.REJECTED,
        CampaignStatus.FAILED,
        CampaignStatus.PENDING_APPROVAL,
        CampaignStatus.MANUAL_REVIEW_REQUIRED,
    ],
)
async def test_workflow_creation_rejects_blocked_campaign_statuses(
    blocked_status: CampaignStatus,
) -> None:
    async with AsyncSessionLocal() as session:
        await create_campaign(session)
        campaign = await CampaignRepository(session).get_by_id_for_update("CL-M3-001")
        assert campaign is not None
        await CampaignRepository(session).update_status(campaign, blocked_status)
        await session.commit()

        with pytest.raises(WorkflowCreationNotAllowedError):
            await WorkflowService(session).create_workflow("CL-M3-001")

        persisted = await CampaignRepository(session).get_by_id("CL-M3-001")
        assert persisted is not None
        assert persisted.status == blocked_status.value


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_e2e_approval_lifecycle() -> None:
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        campaign_response = await client.post(
            "/campaigns",
            json=campaign_payload("CL-E2E-1"),
        )
        assert campaign_response.status_code == 201
        workflow_response = await client.post("/workflows/campaigns/CL-E2E-1")
        assert workflow_response.status_code == 201
        workflow_id = workflow_response.json()["workflow_id"]
        run_response = await client.post(f"/workflows/{workflow_id}/run")
        assert run_response.status_code == 200
        assert run_response.json()["status"] == CampaignStatus.PENDING_APPROVAL

        approval_response = await client.post(
            "/approvals",
            json={
                "campaign_id": "CL-E2E-1",
                "workflow_id": workflow_id,
                "decision": ApprovalDecision.APPROVE,
                "expected_version": 1,
            },
            headers={"x-actor-id": "manager-1", "x-actor-role": UserRole.MANAGER},
        )

        assert approval_response.status_code == 201
        assert approval_response.json()["decision"] == ApprovalDecision.APPROVE


@pytest.mark.asyncio
async def test_revision_workflow_references_parent_and_reaches_approval() -> None:
    async with AsyncSessionLocal() as session:
        await create_campaign(session)
        original = await WorkflowService(session).create_workflow("CL-M3-001")
        original_result = await CampaignWorkflow(
            session,
            MockLLMClient(),
        ).run_to_pending_approval(original.workflow_id)
        assert original_result.status == CampaignStatus.PENDING_APPROVAL
        await ApprovalService(session).decide(
            ApprovalRequest(
                campaign_id="CL-M3-001",
                workflow_id=original.workflow_id,
                decision=ApprovalDecision.REQUEST_REVISION,
                feedback="Revise platform fit.",
                expected_version=1,
            ),
            actor_id="manager-1",
            actor_role=UserRole.MANAGER,
        )

        revision = await WorkflowService(session).create_workflow("CL-M3-001")
        assert revision.parent_workflow_id == original.workflow_id
        assert revision.revision_number == 1
        revision_result = await CampaignWorkflow(
            session,
            MockLLMClient(),
        ).run_to_pending_approval(revision.workflow_id)

        assert revision_result.status == CampaignStatus.PENDING_APPROVAL

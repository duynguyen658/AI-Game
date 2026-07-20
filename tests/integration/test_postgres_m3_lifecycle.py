from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import date
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_llm_client
from app.core.constants import (
    AgentName,
    AgentRunStatus,
    ApprovalDecision,
    CampaignStatus,
    UserRole,
    WorkflowStep,
)
from app.core.exceptions import (
    ApprovalAlreadyDecidedError,
    ApprovalNotAllowedError,
    AgentIterationLimitError,
    LLMProviderError,
    LLMResponseError,
    PersistenceError,
    VersionConflictError,
    WorkflowAlreadyActiveError,
    WorkflowCreationNotAllowedError,
    WorkflowLimitError,
)
from app.database.models import (
    AgentRunModel,
    AgentToolCallModel,
    ApprovalRecordModel,
    CampaignModel,
    WorkflowRunModel,
)
from app.llm.agent_turn import AgentToolRequest, AgentTurn
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


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def api_client() -> AsyncIterator[AsyncClient]:
    from app.main import app

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


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


async def create_pending_workflow(
    session: AsyncSession,
    campaign_id: str = "CL-M3-001",
    llm_client: MockLLMClient | None = None,
):
    await create_campaign(session, campaign_id)
    workflow = await WorkflowService(session).create_workflow(campaign_id)
    result = await CampaignWorkflow(
        session,
        llm_client or MockLLMClient(),
    ).run_to_pending_approval(workflow.workflow_id)
    assert result.status == CampaignStatus.PENDING_APPROVAL
    return result


async def approval_count(session: AsyncSession, workflow_id: UUID) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(ApprovalRecordModel)
        .where(ApprovalRecordModel.workflow_id == workflow_id)
    )
    return result.scalar_one()


async def assert_campaign_and_workflow_rows_are_not_locked(
    campaign_id: str,
    workflow_id: UUID,
) -> None:
    async with AsyncSessionLocal() as lock_session:
        campaign_result = await lock_session.execute(
            select(CampaignModel)
            .where(CampaignModel.campaign_id == campaign_id)
            .with_for_update(nowait=True)
        )
        workflow_result = await lock_session.execute(
            select(WorkflowRunModel)
            .where(WorkflowRunModel.workflow_id == workflow_id)
            .with_for_update(nowait=True)
        )
        assert campaign_result.scalar_one().campaign_id == campaign_id
        assert workflow_result.scalar_one().workflow_id == workflow_id
        await lock_session.rollback()


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
        agent_runs = (
            (
                await session.execute(
                    select(AgentRunModel).where(
                        AgentRunModel.workflow_id == workflow.workflow_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(agent_runs) == 5
        assert all(run.status == AgentRunStatus.COMPLETED.value for run in agent_runs)
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


@pytest.mark.asyncio
async def test_campaign_repository_crud_pagination_and_artifacts(
    db_session: AsyncSession,
) -> None:
    campaign_repo = CampaignRepository(db_session)
    await campaign_repo.create(
        CampaignCreate(
            **campaign_payload("CL-REPO-1"),
        )
    )
    await campaign_repo.create(
        CampaignCreate(
            **campaign_payload("CL-REPO-2"),
        )
    )
    await db_session.commit()

    first_page = await campaign_repo.list(limit=1, offset=0)
    second_page = await campaign_repo.list(limit=1, offset=1)

    assert len(first_page) == 1
    assert len(second_page) == 1
    assert first_page[0].campaign_id != second_page[0].campaign_id

    campaign = await campaign_repo.get_by_id_for_update("CL-REPO-1")
    assert campaign is not None
    analysis = BriefAnalysis(
        summary="Summary",
        campaign_objective="Drive pre-registration",
        target_audience="18-30",
        main_message="Register now",
    )
    await campaign_repo.save_brief_analysis(campaign, analysis)
    await campaign_repo.save_generated_content(campaign, generated_content("repo"))
    await campaign_repo.save_quality_review(campaign, review("PASS", 91))
    await campaign_repo.increment_retry_count(campaign)
    await campaign_repo.increment_version(campaign)
    await campaign_repo.update_status(campaign, CampaignStatus.PENDING_APPROVAL)
    await db_session.commit()

    persisted = await campaign_repo.get_by_id("CL-REPO-1")
    assert persisted is not None
    assert persisted.brief_analysis["summary"] == "Summary"
    assert persisted.generated_content["facebook"]["headline"].startswith("repo")
    assert persisted.quality_review["status"] == "PASS"
    assert persisted.quality_score == 91
    assert persisted.retry_count == 1
    assert persisted.version == 2

    pending = await campaign_repo.list(
        limit=10,
        offset=0,
        status=CampaignStatus.PENDING_APPROVAL,
    )
    assert [campaign.campaign_id for campaign in pending] == ["CL-REPO-1"]


@pytest.mark.asyncio
async def test_workflow_repository_create_revision_and_mutations(
    db_session: AsyncSession,
) -> None:
    await create_campaign(db_session, "CL-WF-REPO")
    workflow_repo = WorkflowRepository(db_session)
    campaign_repo = CampaignRepository(db_session)

    parent = await workflow_repo.create("CL-WF-REPO")
    await workflow_repo.update_status(parent, CampaignStatus.REVISION_REQUIRED)
    await workflow_repo.mark_completed(parent)
    await db_session.commit()

    revision = await workflow_repo.create(
        "CL-WF-REPO",
        status=CampaignStatus.REVISION_REQUIRED,
        current_step=WorkflowStep.HUMAN_REVIEW,
        parent_workflow_id=parent.workflow_id,
        revision_number=1,
    )
    await workflow_repo.increment_llm_call_count(revision)
    await workflow_repo.increment_retry_count(revision)
    await workflow_repo.save_quality_score(revision, 73)
    await workflow_repo.update_status(revision, CampaignStatus.GENERATING)
    await workflow_repo.update_current_step(
        revision,
        WorkflowStep.GENERATE_CONTENT,
    )
    campaign = await campaign_repo.get_by_id_for_update("CL-WF-REPO")
    assert campaign is not None
    await campaign_repo.update_status(campaign, CampaignStatus.GENERATING)
    await db_session.commit()

    active = await workflow_repo.get_active_for_campaign("CL-WF-REPO")
    assert active is not None
    assert active.workflow_id == revision.workflow_id

    history = await workflow_repo.list_for_campaign("CL-WF-REPO")
    assert {workflow.workflow_id for workflow in history} == {
        parent.workflow_id,
        revision.workflow_id,
    }
    assert revision.parent_workflow_id == parent.workflow_id
    assert revision.revision_number == 1
    assert revision.llm_call_count == 1
    assert revision.retry_count == 1
    assert revision.quality_score == 73


@pytest.mark.asyncio
async def test_workflow_repository_rejects_negative_revision_number(
    db_session: AsyncSession,
) -> None:
    await create_campaign(db_session, "CL-WF-NEG")

    with pytest.raises(ValueError, match="revision_number"):
        await WorkflowRepository(db_session).create(
            "CL-WF-NEG",
            revision_number=-1,
        )


@pytest.mark.asyncio
async def test_postgres_constraints_reject_invalid_rows(
    db_session: AsyncSession,
) -> None:
    await create_campaign(db_session, "CL-CONSTRAINT")

    db_session.add(WorkflowRunModel(campaign_id="missing-campaign"))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()

    db_session.add(WorkflowRunModel(campaign_id="CL-CONSTRAINT", retry_count=-1))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()

    db_session.add(WorkflowRunModel(campaign_id="CL-CONSTRAINT", revision_number=-1))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()

    db_session.add(WorkflowRunModel(campaign_id="CL-CONSTRAINT", quality_score=101))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_workflow_service_creation_conflicts_and_unknown_integrity_mapping(
    db_session: AsyncSession,
) -> None:
    await create_campaign(db_session, "CL-SVC-WF")
    service = WorkflowService(db_session)
    await service.create_workflow("CL-SVC-WF")

    with pytest.raises(WorkflowAlreadyActiveError):
        await service.create_workflow("CL-SVC-WF")

    await create_campaign(db_session, "CL-SVC-REV")
    campaign = await CampaignRepository(db_session).get_by_id_for_update("CL-SVC-REV")
    assert campaign is not None
    await CampaignRepository(db_session).update_status(
        campaign,
        CampaignStatus.REVISION_REQUIRED,
    )
    await db_session.commit()

    with pytest.raises(WorkflowCreationNotAllowedError):
        await WorkflowService(db_session).create_workflow("CL-SVC-REV")

    await create_campaign(db_session, "CL-SVC-UNKNOWN")
    unknown_service = WorkflowService(db_session)

    class Diag:
        constraint_name = "uq_unknown_constraint"

    class Orig:
        diag = Diag()

    async def fail_create(*args, **kwargs):
        raise IntegrityError("statement", {}, Orig())

    unknown_service.workflow_repository.create = fail_create

    with pytest.raises(PersistenceError):
        await unknown_service.create_workflow("CL-SVC-UNKNOWN")


@pytest.mark.asyncio
async def test_approval_service_approve_reject_revision_and_conflicts(
    db_session: AsyncSession,
) -> None:
    approved = await create_pending_workflow(db_session, "CL-APPROVE")
    approval = await ApprovalService(db_session).decide(
        ApprovalRequest(
            campaign_id="CL-APPROVE",
            workflow_id=approved.workflow_id,
            decision=ApprovalDecision.APPROVE,
            expected_version=1,
        ),
        actor_id="manager-1",
        actor_role=UserRole.MANAGER,
    )
    assert approval.decision == ApprovalDecision.APPROVE
    assert await approval_count(db_session, approved.workflow_id) == 1

    with pytest.raises(ApprovalAlreadyDecidedError):
        await ApprovalService(db_session).decide(
            ApprovalRequest(
                campaign_id="CL-APPROVE",
                workflow_id=approved.workflow_id,
                decision=ApprovalDecision.APPROVE,
                expected_version=1,
            ),
            actor_id="manager-2",
            actor_role=UserRole.MANAGER,
        )

    rejected = await create_pending_workflow(db_session, "CL-REJECT")
    reject = await ApprovalService(db_session).decide(
        ApprovalRequest(
            campaign_id="CL-REJECT",
            workflow_id=rejected.workflow_id,
            decision=ApprovalDecision.REJECT,
            feedback="Campaign tone is off.",
            expected_version=1,
        ),
        actor_id="manager-1",
        actor_role=UserRole.MANAGER,
    )
    assert reject.decision == ApprovalDecision.REJECT

    revision = await create_pending_workflow(db_session, "CL-REVISION-SVC")
    with pytest.raises(ApprovalNotAllowedError):
        await ApprovalService(db_session).decide(
            ApprovalRequest(
                campaign_id="CL-REVISION-SVC",
                workflow_id=revision.workflow_id,
                decision=ApprovalDecision.REQUEST_REVISION,
                feedback="Needs revision.",
                expected_version=1,
            ),
            actor_id="marketer-1",
            actor_role=UserRole.MARKETING,
        )
    with pytest.raises(VersionConflictError):
        await ApprovalService(db_session).decide(
            ApprovalRequest(
                campaign_id="CL-REVISION-SVC",
                workflow_id=revision.workflow_id,
                decision=ApprovalDecision.REQUEST_REVISION,
                feedback="Needs revision.",
                expected_version=2,
            ),
            actor_id="manager-1",
            actor_role=UserRole.MANAGER,
        )
    request_revision = await ApprovalService(db_session).decide(
        ApprovalRequest(
            campaign_id="CL-REVISION-SVC",
            workflow_id=revision.workflow_id,
            decision=ApprovalDecision.REQUEST_REVISION,
            feedback="Needs revision.",
            expected_version=1,
        ),
        actor_id="manager-1",
        actor_role=UserRole.MANAGER,
    )

    assert request_revision.resulting_version == 2
    old_workflow = await WorkflowRepository(db_session).get_by_id(revision.workflow_id)
    assert old_workflow is not None
    assert old_workflow.status == CampaignStatus.REVISION_REQUIRED.value
    assert old_workflow.completed_at is not None


@pytest.mark.asyncio
async def test_concurrent_workflow_creation_one_succeeds() -> None:
    async with AsyncSessionLocal() as setup_session:
        await create_campaign(setup_session, "CL-CONCURRENT-WF")

    barrier = asyncio.Barrier(2)

    async def attempt_create():
        async with AsyncSessionLocal() as session:
            await barrier.wait()
            try:
                return await WorkflowService(session).create_workflow(
                    "CL-CONCURRENT-WF"
                )
            except WorkflowAlreadyActiveError as exc:
                return exc

    results = await asyncio.gather(attempt_create(), attempt_create())

    assert (
        sum(not isinstance(result, WorkflowAlreadyActiveError) for result in results)
        == 1
    )
    assert (
        sum(isinstance(result, WorkflowAlreadyActiveError) for result in results) == 1
    )

    async with AsyncSessionLocal() as session:
        active = await WorkflowRepository(session).get_active_for_campaign(
            "CL-CONCURRENT-WF"
        )
        assert active is not None
        history = await WorkflowRepository(session).list_for_campaign(
            "CL-CONCURRENT-WF"
        )
        assert len(history) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "first_decision,second_decision,second_feedback",
    [
        (ApprovalDecision.APPROVE, ApprovalDecision.APPROVE, None),
        (ApprovalDecision.APPROVE, ApprovalDecision.REJECT, "Reject instead."),
    ],
)
async def test_concurrent_approval_one_decision_succeeds(
    first_decision: ApprovalDecision,
    second_decision: ApprovalDecision,
    second_feedback: str | None,
) -> None:
    async with AsyncSessionLocal() as setup_session:
        workflow = await create_pending_workflow(setup_session, "CL-CONCURRENT-APP")

    barrier = asyncio.Barrier(2)

    async def attempt_decision(
        decision: ApprovalDecision,
        actor_id: str,
        feedback: str | None,
    ):
        async with AsyncSessionLocal() as session:
            await barrier.wait()
            try:
                return await ApprovalService(session).decide(
                    ApprovalRequest(
                        campaign_id="CL-CONCURRENT-APP",
                        workflow_id=workflow.workflow_id,
                        decision=decision,
                        feedback=feedback,
                        expected_version=1,
                    ),
                    actor_id=actor_id,
                    actor_role=UserRole.MANAGER,
                )
            except ApprovalAlreadyDecidedError as exc:
                return exc

    results = await asyncio.gather(
        attempt_decision(first_decision, "manager-1", None),
        attempt_decision(second_decision, "manager-2", second_feedback),
    )

    assert (
        sum(not isinstance(result, ApprovalAlreadyDecidedError) for result in results)
        == 1
    )
    assert (
        sum(isinstance(result, ApprovalAlreadyDecidedError) for result in results) == 1
    )

    async with AsyncSessionLocal() as session:
        assert await approval_count(session, workflow.workflow_id) == 1


@pytest.mark.asyncio
async def test_concurrent_workflow_execution_and_state_change_conflict() -> None:
    async with AsyncSessionLocal() as setup_session:
        await create_campaign(setup_session, "CL-CONCURRENT-RUN")
        workflow = await WorkflowService(setup_session).create_workflow(
            "CL-CONCURRENT-RUN"
        )
        await WorkflowService(setup_session).transition(
            workflow.workflow_id,
            CampaignStatus.VALIDATING,
            step=WorkflowStep.VALIDATE_INPUT,
        )
        await WorkflowService(setup_session).transition(
            workflow.workflow_id,
            CampaignStatus.ANALYZING,
            step=WorkflowStep.ANALYZE_BRIEF,
        )

    llm_entered = asyncio.Event()
    release_llm = asyncio.Event()

    class BlockingAnalysisLLM(MockLLMClient):
        async def generate_structured(self, **kwargs):
            llm_entered.set()
            await release_llm.wait()
            return await super().generate_structured(**kwargs)

    async with AsyncSessionLocal() as workflow_session:
        runner_task = asyncio.create_task(
            CampaignWorkflow(
                workflow_session,
                BlockingAnalysisLLM(),
            ).run_to_pending_approval(workflow.workflow_id)
        )
        await llm_entered.wait()

        async with AsyncSessionLocal() as competing_session:
            await WorkflowService(competing_session).transition(
                workflow.workflow_id,
                CampaignStatus.FAILED,
                step=WorkflowStep.COMPLETE,
            )

        release_llm.set()
        with pytest.raises(VersionConflictError):
            await runner_task

    async with AsyncSessionLocal() as verify_session:
        campaign = await CampaignRepository(verify_session).get_by_id(
            "CL-CONCURRENT-RUN"
        )
        workflow_model = await WorkflowRepository(verify_session).get_by_id(
            workflow.workflow_id
        )
        assert campaign is not None
        assert workflow_model is not None
        assert campaign.status == CampaignStatus.FAILED.value
        assert workflow_model.status == CampaignStatus.FAILED.value
        assert workflow_model.error_code is None


@pytest.mark.asyncio
async def test_workflow_happy_path_manual_review_and_retry_exhaustion(
    db_session: AsyncSession,
) -> None:
    happy = await create_pending_workflow(db_session, "CL-HAPPY")
    assert happy.llm_call_count == 3
    assert happy.retry_count == 0

    await create_campaign(db_session, "CL-MANUAL")
    manual_workflow = await WorkflowService(db_session).create_workflow("CL-MANUAL")
    manual_result = await CampaignWorkflow(
        db_session,
        MockLLMClient(
            scripted_outputs=[
                BriefAnalysis(
                    summary="Manual summary",
                    campaign_objective="Drive pre-registration",
                    target_audience="18-30",
                    main_message="Register now",
                ),
                generated_content("manual"),
                review("MANUAL_REVIEW_REQUIRED", 52),
            ]
        ),
    ).run_to_pending_approval(manual_workflow.workflow_id)
    assert manual_result.status == CampaignStatus.MANUAL_REVIEW_REQUIRED

    await create_campaign(db_session, "CL-RETRY-EXHAUST")
    retry_workflow = await WorkflowService(db_session).create_workflow(
        "CL-RETRY-EXHAUST"
    )
    retry_runner = CampaignWorkflow(
        db_session,
        MockLLMClient(
            scripted_outputs=[
                BriefAnalysis(
                    summary="Retry summary",
                    campaign_objective="Drive pre-registration",
                    target_audience="18-30",
                    main_message="Register now",
                ),
                generated_content("retry-1"),
                review("FAIL", 40),
                generated_content("retry-2"),
                review("FAIL", 41),
            ]
        ),
    )
    original_content_retries = retry_runner.settings.max_content_retries
    retry_runner.settings.max_content_retries = 1
    try:
        exhausted = await retry_runner.run_to_pending_approval(
            retry_workflow.workflow_id
        )
    finally:
        retry_runner.settings.max_content_retries = original_content_retries
    assert exhausted.status == CampaignStatus.MANUAL_REVIEW_REQUIRED
    assert exhausted.retry_count == 1


@pytest.mark.asyncio
async def test_workflow_execution_failures_are_persisted_safely(
    db_session: AsyncSession,
) -> None:
    await create_campaign(db_session, "CL-BUDGET")
    budget_workflow = await WorkflowService(db_session).create_workflow("CL-BUDGET")
    budget_runner = CampaignWorkflow(db_session, MockLLMClient())
    original_llm_budget = budget_runner.settings.max_llm_calls_per_workflow
    budget_runner.settings.max_llm_calls_per_workflow = 1
    try:
        with pytest.raises(WorkflowLimitError):
            await budget_runner.run_to_pending_approval(budget_workflow.workflow_id)
    finally:
        budget_runner.settings.max_llm_calls_per_workflow = original_llm_budget
    persisted_budget = await WorkflowRepository(db_session).get_by_id(
        budget_workflow.workflow_id
    )
    assert persisted_budget is not None
    assert persisted_budget.status == CampaignStatus.FAILED.value
    assert persisted_budget.error_code == WorkflowLimitError.error_code

    await create_campaign(db_session, "CL-STRUCTURED")
    structured_workflow = await WorkflowService(db_session).create_workflow(
        "CL-STRUCTURED"
    )
    with pytest.raises(LLMResponseError):
        await CampaignWorkflow(
            db_session,
            MockLLMClient(scripted_outputs=[generated_content("wrong-schema")]),
        ).run_to_pending_approval(structured_workflow.workflow_id)
    persisted_structured = await WorkflowRepository(db_session).get_by_id(
        structured_workflow.workflow_id
    )
    assert persisted_structured is not None
    assert persisted_structured.status == CampaignStatus.FAILED.value
    assert persisted_structured.error_code == LLMResponseError.error_code


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "resume_status",
    [
        CampaignStatus.ANALYZING,
        CampaignStatus.GENERATING,
        CampaignStatus.REVIEWING,
    ],
)
async def test_workflow_resumes_from_intermediate_states(
    db_session: AsyncSession,
    resume_status: CampaignStatus,
) -> None:
    campaign_id = f"CL-RESUME-{resume_status.value}"
    await create_campaign(db_session, campaign_id)
    workflow = await WorkflowService(db_session).create_workflow(campaign_id)
    campaign_repo = CampaignRepository(db_session)
    workflow_repo = WorkflowRepository(db_session)
    campaign = await campaign_repo.get_by_id_for_update(campaign_id)
    workflow_model = await workflow_repo.get_by_id_for_update(workflow.workflow_id)
    assert campaign is not None
    assert workflow_model is not None

    if resume_status in {CampaignStatus.GENERATING, CampaignStatus.REVIEWING}:
        await campaign_repo.save_brief_analysis(
            campaign,
            BriefAnalysis(
                summary="Resume summary",
                campaign_objective="Drive pre-registration",
                target_audience="18-30",
                main_message="Register now",
            ),
        )
    if resume_status == CampaignStatus.REVIEWING:
        await campaign_repo.save_generated_content(
            campaign, generated_content("resume")
        )
    await workflow_repo.update_status(workflow_model, resume_status)
    await campaign_repo.update_status(campaign, resume_status)
    await db_session.commit()

    result = await CampaignWorkflow(
        db_session,
        MockLLMClient(),
    ).run_to_pending_approval(workflow.workflow_id)
    assert result.status == CampaignStatus.PENDING_APPROVAL


@pytest.mark.asyncio
async def test_workflow_does_not_hold_transaction_during_llm_calls(
    db_session: AsyncSession,
) -> None:
    await create_campaign(db_session, "CL-NO-TX")
    workflow = await WorkflowService(db_session).create_workflow("CL-NO-TX")

    class TransactionCheckingLLM(MockLLMClient):
        async def generate_structured(self, **kwargs):
            assert not db_session.in_transaction()
            await assert_campaign_and_workflow_rows_are_not_locked(
                "CL-NO-TX",
                workflow.workflow_id,
            )
            return await super().generate_structured(**kwargs)

    result = await CampaignWorkflow(
        db_session,
        TransactionCheckingLLM(),
    ).run_to_pending_approval(workflow.workflow_id)

    assert result.status == CampaignStatus.PENDING_APPROVAL


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_api_campaign_workflow_approval_and_error_responses(
    api_client: AsyncClient,
) -> None:
    health = await api_client.get("/health")
    ready = await api_client.get("/ready")
    assert health.status_code == 200
    assert ready.status_code == 200

    invalid_campaign = await api_client.post(
        "/campaigns",
        json={**campaign_payload("bad id")},
    )
    assert invalid_campaign.status_code == 422

    missing_campaign = await api_client.get("/campaigns/CL-MISSING")
    assert missing_campaign.status_code == 404
    assert "traceback" not in missing_campaign.text.lower()

    created = await api_client.post("/campaigns", json=campaign_payload("CL-API-1"))
    assert created.status_code == 201
    listed = await api_client.get("/campaigns", params={"status": "RECEIVED"})
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    fetched = await api_client.get("/campaigns/CL-API-1")
    assert fetched.status_code == 200

    workflow_response = await api_client.post("/workflows/campaigns/CL-API-1")
    assert workflow_response.status_code == 201
    workflow_id = workflow_response.json()["workflow_id"]

    duplicate_workflow = await api_client.post("/workflows/campaigns/CL-API-1")
    assert duplicate_workflow.status_code == 409

    missing_workflow = await api_client.get(f"/workflows/{uuid4()}")
    assert missing_workflow.status_code == 404

    run_response = await api_client.post(f"/workflows/{workflow_id}/run")
    assert run_response.status_code == 200
    assert run_response.json()["status"] == CampaignStatus.PENDING_APPROVAL

    unauthenticated = await api_client.post(
        "/approvals",
        json={
            "campaign_id": "CL-API-1",
            "workflow_id": workflow_id,
            "decision": ApprovalDecision.APPROVE,
            "expected_version": 1,
        },
    )
    assert unauthenticated.status_code == 401

    unauthorized = await api_client.post(
        "/approvals",
        json={
            "campaign_id": "CL-API-1",
            "workflow_id": workflow_id,
            "decision": ApprovalDecision.APPROVE,
            "expected_version": 1,
        },
        headers={"x-actor-id": "marketer-1", "x-actor-role": UserRole.MARKETING},
    )
    assert unauthorized.status_code == 403

    approval = await api_client.post(
        "/approvals",
        json={
            "campaign_id": "CL-API-1",
            "workflow_id": workflow_id,
            "decision": ApprovalDecision.APPROVE,
            "expected_version": 1,
        },
        headers={"x-actor-id": "manager-1", "x-actor-role": UserRole.MANAGER},
    )
    assert approval.status_code == 201

    duplicate_approval = await api_client.post(
        "/approvals",
        json={
            "campaign_id": "CL-API-1",
            "workflow_id": workflow_id,
            "decision": ApprovalDecision.APPROVE,
            "expected_version": 1,
        },
        headers={"x-actor-id": "manager-2", "x-actor-role": UserRole.MANAGER},
    )
    assert duplicate_approval.status_code == 409
    assert "duplicate key" not in duplicate_approval.text.lower()


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_api_e2e_revision_failure_and_retry_flows(
    api_client: AsyncClient,
) -> None:
    from app.main import app

    await api_client.post("/campaigns", json=campaign_payload("CL-API-REV"))
    original_response = await api_client.post("/workflows/campaigns/CL-API-REV")
    original_workflow_id = original_response.json()["workflow_id"]
    await api_client.post(f"/workflows/{original_workflow_id}/run")
    revision_request = await api_client.post(
        "/approvals",
        json={
            "campaign_id": "CL-API-REV",
            "workflow_id": original_workflow_id,
            "decision": ApprovalDecision.REQUEST_REVISION,
            "feedback": "Revise this.",
            "expected_version": 1,
        },
        headers={"x-actor-id": "manager-1", "x-actor-role": UserRole.MANAGER},
    )
    assert revision_request.status_code == 201

    revision_response = await api_client.post("/workflows/campaigns/CL-API-REV")
    assert revision_response.status_code == 201
    revision_payload = revision_response.json()
    assert revision_payload["parent_workflow_id"] == original_workflow_id
    assert revision_payload["revision_number"] == 1
    await api_client.post(f"/workflows/{revision_payload['workflow_id']}/run")
    revision_approval = await api_client.post(
        "/approvals",
        json={
            "campaign_id": "CL-API-REV",
            "workflow_id": revision_payload["workflow_id"],
            "decision": ApprovalDecision.APPROVE,
            "expected_version": 2,
        },
        headers={"x-actor-id": "manager-1", "x-actor-role": UserRole.MANAGER},
    )
    assert revision_approval.status_code == 201

    failure_client = MockLLMClient(
        scripted_outputs=[LLMProviderError("api_key=real-secret Bearer bad.token")]
    )
    app.dependency_overrides[get_llm_client] = lambda: failure_client
    await api_client.post("/campaigns", json=campaign_payload("CL-API-FAIL"))
    failure_workflow = await api_client.post("/workflows/campaigns/CL-API-FAIL")
    failure_workflow_id = failure_workflow.json()["workflow_id"]
    failure_run = await api_client.post(f"/workflows/{failure_workflow_id}/run")
    assert failure_run.status_code == 500
    persisted_failure = await api_client.get(f"/workflows/{failure_workflow_id}")
    assert persisted_failure.json()["status"] == CampaignStatus.FAILED
    assert "real-secret" not in str(persisted_failure.json())
    app.dependency_overrides.clear()

    retry_client = MockLLMClient(
        scripted_outputs=[
            BriefAnalysis(
                summary="Retry API summary",
                campaign_objective="Drive pre-registration",
                target_audience="18-30",
                main_message="Register now",
            ),
            generated_content("api-retry-1"),
            review("FAIL", 44),
            generated_content("api-retry-2"),
            review("PASS", 90),
        ]
    )
    app.dependency_overrides[get_llm_client] = lambda: retry_client
    await api_client.post("/campaigns", json=campaign_payload("CL-API-RETRY"))
    retry_workflow = await api_client.post("/workflows/campaigns/CL-API-RETRY")
    retry_run = await api_client.post(
        f"/workflows/{retry_workflow.json()['workflow_id']}/run"
    )
    assert retry_run.status_code == 200
    assert retry_run.json()["status"] == CampaignStatus.PENDING_APPROVAL
    assert retry_run.json()["retry_count"] == 1
    assert retry_run.json()["llm_call_count"] == 5


@pytest.mark.asyncio
async def test_agentic_happy_path_persists_runs_tools_and_query_api(
    db_session: AsyncSession,
    api_client: AsyncClient,
) -> None:
    campaign_id = "CL-M4-HAPPY"
    await create_campaign(db_session, campaign_id)
    workflow = await WorkflowService(db_session).create_workflow(campaign_id)
    analysis = BriefAnalysis(
        summary="Campaign summary",
        campaign_objective="Drive pre-registration",
        target_audience="18-30",
        main_message="Register now",
    )
    client = MockLLMClient(
        scripted_turns=[
            AgentTurn(
                tool_calls=[
                    AgentToolRequest(
                        tool_call_id="brief-campaign",
                        tool_name="get_campaign",
                        arguments={"campaign_id": campaign_id},
                    )
                ]
            ),
            AgentTurn(final_output=analysis.model_dump(mode="json")),
            AgentTurn(final_output=generated_content().model_dump(mode="json")),
            AgentTurn(final_output=review("PASS").model_dump(mode="json")),
        ]
    )

    result = await CampaignWorkflow(db_session, client).run_to_pending_approval(
        workflow.workflow_id
    )
    assert result.status == CampaignStatus.PENDING_APPROVAL
    assert result.llm_call_count == 4

    runs = (
        (
            await db_session.execute(
                select(AgentRunModel)
                .where(AgentRunModel.workflow_id == workflow.workflow_id)
                .order_by(AgentRunModel.started_at)
            )
        )
        .scalars()
        .all()
    )
    assert [run.agent_name for run in runs] == [
        AgentName.BRIEF_ANALYST.value,
        AgentName.CONTENT_GENERATOR.value,
        AgentName.CONTENT_REVIEWER.value,
    ]
    assert [run.llm_call_count for run in runs] == [2, 1, 1]
    assert all(run.status == AgentRunStatus.COMPLETED.value for run in runs)
    tool_calls = (await db_session.execute(select(AgentToolCallModel))).scalars().all()
    assert len(tool_calls) == 1
    assert tool_calls[0].status == "COMPLETED"

    response = await api_client.get(f"/workflows/{workflow.workflow_id}/agent-runs")
    assert response.status_code == 200
    assert len(response.json()) == 3
    response = await api_client.get(f"/agent-runs/{runs[0].agent_run_id}/tool-calls")
    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.asyncio
async def test_agent_iteration_limit_persists_run_and_workflow_failure(
    db_session: AsyncSession,
) -> None:
    campaign_id = "CL-M4-LIMIT"
    await create_campaign(db_session, campaign_id)
    workflow = await WorkflowService(db_session).create_workflow(campaign_id)
    turns = [
        AgentTurn(
            tool_calls=[
                AgentToolRequest(
                    tool_call_id=f"campaign-{index}",
                    tool_name="get_campaign",
                    arguments={"campaign_id": campaign_id},
                )
            ]
        )
        for index in range(5)
    ]

    with pytest.raises(AgentIterationLimitError, match="iteration budget exhausted"):
        await CampaignWorkflow(
            db_session, MockLLMClient(scripted_turns=turns)
        ).run_to_pending_approval(workflow.workflow_id)

    run = (
        await db_session.execute(
            select(AgentRunModel).where(
                AgentRunModel.workflow_id == workflow.workflow_id
            )
        )
    ).scalar_one()
    await db_session.refresh(run)
    stored_workflow = await db_session.get(WorkflowRunModel, workflow.workflow_id)
    assert run.status == AgentRunStatus.LIMIT_EXCEEDED.value
    assert run.iteration_count == 5
    assert run.llm_call_count == 5
    assert run.tool_call_count == 5
    assert stored_workflow is not None
    assert stored_workflow.status == CampaignStatus.FAILED.value

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.actions.campaign_actions import (
    InternalActionResult,
    InternalRecommendationInput,
)
from app.agentic.actions.definitions import ActionDefinition, ActionExecutionGuard
from app.agentic.actions.registry import ActionRegistry
from app.core.constants import (
    ActionExecutionStatus,
    ActionRequestStatus,
    AgentName,
    ApprovalDecision,
    CampaignStatus,
    MemoryEventType,
    MemoryRecordStatus,
    PolicyDecision,
    UserRole,
)
from app.core.exceptions import (
    ActionExecutionConflictError,
    ActionExpiredError,
    ActionPolicyApprovalRequiredError,
    ActionPolicyReevaluationDeniedError,
    ActionStateChangedError,
    ActionVersionConflictError,
    ControlledActionExecutionError,
    PersistenceError,
)
from app.database.models import (
    AgentActionExecutionModel,
    AgentActionRequestModel,
    AgentMemoryEntryModel,
)
from app.database.session import AsyncSessionLocal
from app.repositories.action_request_repository import ActionRequestRepository
from app.schemas.action_request import AgentActionProposal
from app.schemas.agent_run import AgentRunCreate
from app.schemas.approval import ApprovalRequest
from app.schemas.campaign import CampaignCreate
from app.service.action_service import ActionService
from app.service.action_state_guard_service import ActionStateGuardService
from app.service.agent_run_service import AgentRunService
from app.service.approval_service import ApprovalService
from app.service.auth_service import AuthenticatedActor
from app.service.campaign_service import CampaignService
from app.service.memory_service import MemoryService
from app.service.workflow_service import WorkflowService
from app.llm.agent_turn import AgentTurn
from app.llm.mock_client import MockLLMClient
from app.schemas.campaign import BriefAnalysis
from app.workflows.campaign_workflow import CampaignWorkflow

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("RUN_POSTGRES_TESTS") != "1",
        reason="set RUN_POSTGRES_TESTS=1 to run PostgreSQL integration tests",
    ),
]


@pytest_asyncio.fixture(autouse=True)
async def clean_m5_database() -> AsyncIterator[None]:
    statement = text(
        "TRUNCATE agent_memory_entries, agent_action_executions, "
        "agent_action_requests, agent_tool_calls, agent_runs, approval_records, "
        "workflow_runs, campaigns, security_events RESTART IDENTITY CASCADE"
    )
    async with AsyncSessionLocal() as session:
        await session.execute(statement)
        await session.commit()
    yield
    async with AsyncSessionLocal() as session:
        await session.execute(statement)
        await session.commit()


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def api_client() -> AsyncIterator[AsyncClient]:
    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


async def create_scope(
    session: AsyncSession,
    *,
    campaign_id: str,
    status: CampaignStatus,
    agent_name: AgentName,
):
    await CampaignService(session).create_campaign(
        CampaignCreate(
            campaign_id=campaign_id,
            game_name="Cyber Legends",
            genre="Action RPG",
            target_audience="18-30",
            market="Vietnam",
            platforms=["Facebook"],
            campaign_objective="Drive registration",
            tone="Cyberpunk",
            launch_date=date(2026, 8, 15),
            promotion="500 gems",
            raw_brief="Internal campaign",
        )
    )
    workflow = await WorkflowService(session).create_workflow(campaign_id)
    path = {
        CampaignStatus.RECEIVED: [],
        CampaignStatus.ANALYZING: [
            CampaignStatus.VALIDATING,
            CampaignStatus.ANALYZING,
        ],
        CampaignStatus.GENERATING: [
            CampaignStatus.VALIDATING,
            CampaignStatus.ANALYZING,
            CampaignStatus.GENERATING,
        ],
        CampaignStatus.REVIEWING: [
            CampaignStatus.VALIDATING,
            CampaignStatus.ANALYZING,
            CampaignStatus.GENERATING,
            CampaignStatus.REVIEWING,
        ],
    }[status]
    for next_status in path:
        workflow = await WorkflowService(session).transition(
            workflow.workflow_id, next_status
        )
    run = await AgentRunService(session).create_run(
        AgentRunCreate(
            workflow_id=workflow.workflow_id,
            campaign_id=campaign_id,
            agent_name=agent_name,
            model="mock",
            prompt_version="m5-v1",
        )
    )
    await AgentRunService(session).start_run(run.agent_run_id)
    return workflow, run


def proposal(action_name: str, workflow, **arguments) -> AgentActionProposal:
    return AgentActionProposal(
        action_name=action_name,
        arguments={
            "campaign_id": workflow.campaign_id,
            "workflow_id": workflow.workflow_id,
            "revision_number": workflow.revision_number,
            **arguments,
        },
        rationale_summary="Short operational reason token=private-value",
    )


def recommendation_definition(
    handler,
    *,
    policy: PolicyDecision,
    required_role: UserRole | None = None,
) -> ActionDefinition:
    return ActionDefinition(
        name="create_internal_recommendation",
        description="Controlled policy freshness test action",
        input_model=InternalRecommendationInput,
        output_model=InternalActionResult,
        default_policy=policy,
        reversible=True,
        allowed_agents=frozenset({AgentName.BRIEF_ANALYST}),
        handler=handler,
        required_role=required_role,
        allowed_campaign_statuses=frozenset({CampaignStatus.ANALYZING}),
        allowed_workflow_statuses=frozenset({CampaignStatus.ANALYZING}),
        approval_ttl_seconds=(
            3600 if policy == PolicyDecision.APPROVAL_REQUIRED else None
        ),
    )


class SequencedActionRegistry(ActionRegistry):
    def __init__(self, definitions: list[ActionDefinition]) -> None:
        super().__init__(definitions[:1])
        self.definitions = definitions
        self.index = 0

    def get(self, name: str) -> ActionDefinition:
        definition = self.definitions[min(self.index, len(self.definitions) - 1)]
        self.index += 1
        if definition.name != name:
            return super().get(name)
        return definition


@pytest.mark.asyncio
async def test_safe_and_forbidden_actions_are_audited_and_idempotent(
    db_session: AsyncSession,
) -> None:
    workflow, run = await create_scope(
        db_session,
        campaign_id="CL-M5-SAFE",
        status=CampaignStatus.ANALYZING,
        agent_name=AgentName.BRIEF_ANALYST,
    )
    service = ActionService(db_session)
    safe = proposal(
        "create_internal_recommendation",
        workflow,
        recommendation="Emphasize pre-registration rewards",
    )
    first = await service.propose(
        agent_run_id=run.agent_run_id,
        agent_name=AgentName.BRIEF_ANALYST,
        proposal=safe,
    )
    duplicate = await service.propose(
        agent_run_id=run.agent_run_id,
        agent_name=AgentName.BRIEF_ANALYST,
        proposal=safe,
    )
    denied = await service.propose(
        agent_run_id=run.agent_run_id,
        agent_name=AgentName.BRIEF_ANALYST,
        proposal=AgentActionProposal(
            action_name="publish-campaign",
            arguments={"campaign_id": workflow.campaign_id},
            rationale_summary="Publish without permission",
        ),
    )

    assert first.action_request.status == ActionRequestStatus.COMPLETED
    assert first.execution_status == ActionExecutionStatus.COMPLETED.value
    assert (
        duplicate.action_request.action_request_id
        == first.action_request.action_request_id
    )
    assert denied.action_request.status == ActionRequestStatus.REJECTED
    assert denied.action_request.policy_decision == PolicyDecision.FORBIDDEN
    executions = (
        (await db_session.execute(select(AgentActionExecutionModel))).scalars().all()
    )
    assert len(executions) == 1
    memories = (await db_session.execute(select(AgentMemoryEntryModel))).scalars().all()
    assert {item.event_type for item in memories} >= {
        MemoryEventType.ACTION_PROPOSED.value,
        MemoryEventType.POLICY_DECIDED.value,
        MemoryEventType.ACTION_COMPLETED.value,
        MemoryEventType.ACTION_REJECTED.value,
    }
    assert "private-value" not in str(memories)


@pytest.mark.asyncio
async def test_approval_rejection_expiration_and_version_conflict(
    db_session: AsyncSession,
) -> None:
    workflow, run = await create_scope(
        db_session,
        campaign_id="CL-M5-APPROVAL",
        status=CampaignStatus.REVIEWING,
        agent_name=AgentName.CONTENT_REVIEWER,
    )
    service = ActionService(db_session)
    manager = AuthenticatedActor(actor_id="manager-1", role=UserRole.MANAGER)
    pending = await service.propose(
        agent_run_id=run.agent_run_id,
        agent_name=AgentName.CONTENT_REVIEWER,
        proposal=proposal("add_manual_review_note", workflow, note="Check CTA"),
    )
    assert pending.action_request.status == ActionRequestStatus.PENDING_APPROVAL
    approved = await service.approve(
        pending.action_request.action_request_id,
        actor=manager,
        expected_version=pending.action_request.version,
    )
    with pytest.raises(ActionVersionConflictError):
        await service.approve(
            approved.action_request_id,
            actor=manager,
            expected_version=pending.action_request.version,
        )
    execution = await service.execute(
        approved.action_request_id,
        actor=manager,
        expected_version=approved.version,
    )
    assert execution.status == ActionExecutionStatus.COMPLETED

    rejected_pending = await service.propose(
        agent_run_id=run.agent_run_id,
        agent_name=AgentName.CONTENT_REVIEWER,
        proposal=proposal("add_manual_review_note", workflow, note="Reject this note"),
    )
    rejected = await service.reject(
        rejected_pending.action_request.action_request_id,
        actor=manager,
        expected_version=rejected_pending.action_request.version,
        reason="Not needed",
    )
    assert rejected.status == ActionRequestStatus.REJECTED

    expired_pending = await service.propose(
        agent_run_id=run.agent_run_id,
        agent_name=AgentName.CONTENT_REVIEWER,
        proposal=proposal("add_manual_review_note", workflow, note="Expired note"),
    )
    expired_model = await ActionRequestRepository(db_session).get_by_id(
        expired_pending.action_request.action_request_id
    )
    assert expired_model is not None
    expired_model.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    with pytest.raises(ActionExpiredError):
        await service.approve(
            expired_model.action_request_id,
            actor=manager,
            expected_version=expired_model.version,
        )
    assert (
        await service.get(expired_model.action_request_id)
    ).status == ActionRequestStatus.EXPIRED


@pytest.mark.asyncio
async def test_concurrent_approval_has_one_winner(db_session: AsyncSession) -> None:
    workflow, run = await create_scope(
        db_session,
        campaign_id="CL-M5-CONCURRENT",
        status=CampaignStatus.REVIEWING,
        agent_name=AgentName.CONTENT_REVIEWER,
    )
    pending = await ActionService(db_session).propose(
        agent_run_id=run.agent_run_id,
        agent_name=AgentName.CONTENT_REVIEWER,
        proposal=proposal("add_manual_review_note", workflow, note="Concurrent note"),
    )
    actor = AuthenticatedActor(actor_id="manager-concurrent", role=UserRole.MANAGER)

    async def approve_once():
        async with AsyncSessionLocal() as session:
            return await ActionService(session).approve(
                pending.action_request.action_request_id,
                actor=actor,
                expected_version=pending.action_request.version,
            )

    results = await asyncio.gather(
        approve_once(), approve_once(), return_exceptions=True
    )
    assert sum(not isinstance(item, Exception) for item in results) == 1
    assert sum(isinstance(item, ActionVersionConflictError) for item in results) == 1


@pytest.mark.asyncio
async def test_concurrent_approve_and_reject_have_one_decision(
    db_session: AsyncSession,
) -> None:
    workflow, run = await create_scope(
        db_session,
        campaign_id="CL-M5-DECISION-RACE",
        status=CampaignStatus.REVIEWING,
        agent_name=AgentName.CONTENT_REVIEWER,
    )
    pending = await ActionService(db_session).propose(
        agent_run_id=run.agent_run_id,
        agent_name=AgentName.CONTENT_REVIEWER,
        proposal=proposal("add_manual_review_note", workflow, note="Race decision"),
    )
    actor = AuthenticatedActor(actor_id="manager-decision", role=UserRole.MANAGER)
    barrier = asyncio.Barrier(2)

    async def approve_once():
        async with AsyncSessionLocal() as session:
            await barrier.wait()
            return await ActionService(session).approve(
                pending.action_request.action_request_id,
                actor=actor,
                expected_version=pending.action_request.version,
            )

    async def reject_once():
        async with AsyncSessionLocal() as session:
            await barrier.wait()
            return await ActionService(session).reject(
                pending.action_request.action_request_id,
                actor=actor,
                expected_version=pending.action_request.version,
                reason="Concurrent rejection",
            )

    results = await asyncio.gather(
        approve_once(), reject_once(), return_exceptions=True
    )
    assert sum(not isinstance(item, Exception) for item in results) == 1
    assert sum(isinstance(item, ActionVersionConflictError) for item in results) == 1
    final = await ActionService(db_session).get(
        pending.action_request.action_request_id
    )
    assert final.status in {ActionRequestStatus.APPROVED, ActionRequestStatus.REJECTED}


@pytest.mark.asyncio
async def test_concurrent_approve_and_expire_have_one_transition(
    db_session: AsyncSession,
) -> None:
    workflow, run = await create_scope(
        db_session,
        campaign_id="CL-M5-EXPIRY-RACE",
        status=CampaignStatus.REVIEWING,
        agent_name=AgentName.CONTENT_REVIEWER,
    )
    pending = await ActionService(db_session).propose(
        agent_run_id=run.agent_run_id,
        agent_name=AgentName.CONTENT_REVIEWER,
        proposal=proposal("add_manual_review_note", workflow, note="Race expiration"),
    )
    actor = AuthenticatedActor(actor_id="manager-expiry", role=UserRole.MANAGER)
    barrier = asyncio.Barrier(2)

    async def approve_once():
        async with AsyncSessionLocal() as session:
            await barrier.wait()
            return await ActionService(session).approve(
                pending.action_request.action_request_id,
                actor=actor,
                expected_version=pending.action_request.version,
            )

    async def expire_once():
        async with AsyncSessionLocal() as session:
            await barrier.wait()
            updated = await ActionRequestRepository(session).expire(
                pending.action_request.action_request_id,
                expected_version=pending.action_request.version,
            )
            await session.commit()
            return updated

    results = await asyncio.gather(
        approve_once(), expire_once(), return_exceptions=True
    )
    wins = sum(
        (not isinstance(item, Exception)) and item is not False for item in results
    )
    conflicts = sum(
        isinstance(item, ActionVersionConflictError) or item is False
        for item in results
    )
    assert wins == 1
    assert conflicts == 1
    final = await ActionService(db_session).get(
        pending.action_request.action_request_id
    )
    assert final.status in {ActionRequestStatus.APPROVED, ActionRequestStatus.EXPIRED}


@pytest.mark.asyncio
async def test_concurrent_duplicate_safe_proposal_executes_once(
    db_session: AsyncSession,
) -> None:
    workflow, run = await create_scope(
        db_session,
        campaign_id="CL-M5-DUPLICATE-RACE",
        status=CampaignStatus.ANALYZING,
        agent_name=AgentName.BRIEF_ANALYST,
    )
    safe = proposal(
        "create_internal_recommendation",
        workflow,
        recommendation="Concurrent safe action",
    )
    barrier = asyncio.Barrier(2)

    async def propose_once():
        async with AsyncSessionLocal() as session:
            await barrier.wait()
            return await ActionService(session).propose(
                agent_run_id=run.agent_run_id,
                agent_name=AgentName.BRIEF_ANALYST,
                proposal=safe,
            )

    results = await asyncio.gather(propose_once(), propose_once())
    assert (
        results[0].action_request.action_request_id
        == results[1].action_request.action_request_id
    )
    requests = (
        (await db_session.execute(select(AgentActionRequestModel))).scalars().all()
    )
    executions = (
        (await db_session.execute(select(AgentActionExecutionModel))).scalars().all()
    )
    assert len(requests) == 1
    assert len(executions) == 1
    assert requests[0].status == ActionRequestStatus.COMPLETED.value
    assert executions[0].status == ActionExecutionStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_concurrent_execution_has_one_side_effect(
    db_session: AsyncSession,
) -> None:
    workflow, run = await create_scope(
        db_session,
        campaign_id="CL-M5-EXECUTE-RACE",
        status=CampaignStatus.REVIEWING,
        agent_name=AgentName.CONTENT_REVIEWER,
    )
    manager = AuthenticatedActor(actor_id="manager-race", role=UserRole.MANAGER)
    pending = await ActionService(db_session).propose(
        agent_run_id=run.agent_run_id,
        agent_name=AgentName.CONTENT_REVIEWER,
        proposal=proposal("add_manual_review_note", workflow, note="Execute once"),
    )
    approved = await ActionService(db_session).approve(
        pending.action_request.action_request_id,
        actor=manager,
        expected_version=pending.action_request.version,
    )

    async def execute_once():
        async with AsyncSessionLocal() as session:
            return await ActionService(session).execute(
                approved.action_request_id,
                actor=manager,
                expected_version=approved.version,
            )

    results = await asyncio.gather(
        execute_once(), execute_once(), return_exceptions=True
    )
    assert sum(not isinstance(item, Exception) for item in results) == 1
    assert sum(isinstance(item, ActionExecutionConflictError) for item in results) == 1
    executions = (
        (await db_session.execute(select(AgentActionExecutionModel))).scalars().all()
    )
    assert len(executions) == 1
    assert executions[0].status == ActionExecutionStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_execution_failure_and_cancellation_are_terminal(
    db_session: AsyncSession,
) -> None:
    workflow, run = await create_scope(
        db_session,
        campaign_id="CL-M5-TERMINAL",
        status=CampaignStatus.ANALYZING,
        agent_name=AgentName.BRIEF_ANALYST,
    )

    async def fail(
        _: InternalRecommendationInput, __: ActionExecutionGuard
    ) -> InternalActionResult:
        raise RuntimeError("password=private-action-secret")

    failing_registry = ActionRegistry(
        [
            ActionDefinition(
                name="create_internal_recommendation",
                description="Fail safely",
                input_model=InternalRecommendationInput,
                output_model=InternalActionResult,
                default_policy=PolicyDecision.SAFE,
                reversible=True,
                allowed_agents=frozenset({AgentName.BRIEF_ANALYST}),
                handler=fail,
                allowed_campaign_statuses=frozenset({CampaignStatus.ANALYZING}),
                allowed_workflow_statuses=frozenset({CampaignStatus.ANALYZING}),
            )
        ]
    )
    failing = ActionService(db_session, registry=failing_registry)
    with pytest.raises(ControlledActionExecutionError):
        await failing.propose(
            agent_run_id=run.agent_run_id,
            agent_name=AgentName.BRIEF_ANALYST,
            proposal=proposal(
                "create_internal_recommendation", workflow, recommendation="Fail"
            ),
        )
    request = (await db_session.execute(select(AgentActionRequestModel))).scalar_one()
    execution = (
        await db_session.execute(select(AgentActionExecutionModel))
    ).scalar_one()
    assert request.status == ActionRequestStatus.FAILED.value
    assert execution.status == ActionExecutionStatus.FAILED.value
    assert "private-action-secret" not in (execution.error_message or "")

    await db_session.execute(
        text(
            "TRUNCATE agent_memory_entries, agent_action_executions, "
            "agent_action_requests RESTART IDENTITY CASCADE"
        )
    )
    await db_session.commit()
    started = asyncio.Event()

    async def block(
        _: InternalRecommendationInput, __: ActionExecutionGuard
    ) -> InternalActionResult:
        started.set()
        await asyncio.Event().wait()
        return InternalActionResult(summary="unreachable", changed=False)

    blocking_registry = ActionRegistry(
        [
            ActionDefinition(
                name="create_internal_recommendation",
                description="Block until cancellation",
                input_model=InternalRecommendationInput,
                output_model=InternalActionResult,
                default_policy=PolicyDecision.SAFE,
                reversible=True,
                allowed_agents=frozenset({AgentName.BRIEF_ANALYST}),
                handler=block,
                allowed_campaign_statuses=frozenset({CampaignStatus.ANALYZING}),
                allowed_workflow_statuses=frozenset({CampaignStatus.ANALYZING}),
            )
        ]
    )
    task = asyncio.create_task(
        ActionService(db_session, registry=blocking_registry).propose(
            agent_run_id=run.agent_run_id,
            agent_name=AgentName.BRIEF_ANALYST,
            proposal=proposal(
                "create_internal_recommendation", workflow, recommendation="Cancel"
            ),
        )
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    execution = (
        await db_session.execute(select(AgentActionExecutionModel))
    ).scalar_one()
    request = (await db_session.execute(select(AgentActionRequestModel))).scalar_one()
    assert execution.status == ActionExecutionStatus.CANCELLED.value
    assert request.status == ActionRequestStatus.FAILED.value


@pytest.mark.asyncio
async def test_memory_redaction_expiration_and_api_security(
    db_session: AsyncSession, api_client: AsyncClient
) -> None:
    workflow, run = await create_scope(
        db_session,
        campaign_id="CL-M5-MEMORY",
        status=CampaignStatus.ANALYZING,
        agent_name=AgentName.BRIEF_ANALYST,
    )
    memory = await MemoryService(db_session).record_event(
        campaign_id=workflow.campaign_id,
        workflow_id=workflow.workflow_id,
        agent_run_id=run.agent_run_id,
        event_type=MemoryEventType.ACTION_FAILED,
        summary="token=private-memory-token",
        metadata={"password": "private", "safe": "visible"},
    )
    assert "private-memory-token" not in memory.summary
    assert "password" not in memory.metadata

    expired = await MemoryService(db_session).record_event(
        campaign_id=workflow.campaign_id,
        workflow_id=workflow.workflow_id,
        event_type=MemoryEventType.ACTION_FAILED,
        summary="Old failure",
    )
    expired_model = await db_session.get(AgentMemoryEntryModel, expired.memory_entry_id)
    assert expired_model is not None
    expired_model.created_at = datetime.now(UTC) - timedelta(days=2)
    expired_model.expires_at = datetime.now(UTC) - timedelta(days=1)
    await db_session.commit()

    headers = {"x-actor-id": "manager-1", "x-actor-role": "manager"}
    route = f"/campaigns/{workflow.campaign_id}/memories"
    assert (await api_client.get(route)).status_code == 401
    assert (
        await api_client.get(
            route,
            headers={"x-actor-id": "marketing-1", "x-actor-role": "marketing"},
        )
    ).status_code == 403
    response = await api_client.get(route, headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert "private-memory-token" not in response.text
    workflow_response = await api_client.get(
        f"/workflows/{workflow.workflow_id}/memories"
        f"?event_type={MemoryEventType.ACTION_FAILED.value}",
        headers=headers,
    )
    assert workflow_response.status_code == 200
    assert len(workflow_response.json()) == 1


@pytest.mark.asyncio
async def test_action_api_auth_pagination_and_missing(
    db_session: AsyncSession, api_client: AsyncClient
) -> None:
    workflow, run = await create_scope(
        db_session,
        campaign_id="CL-M5-API",
        status=CampaignStatus.REVIEWING,
        agent_name=AgentName.CONTENT_REVIEWER,
    )
    pending = await ActionService(db_session).propose(
        agent_run_id=run.agent_run_id,
        agent_name=AgentName.CONTENT_REVIEWER,
        proposal=proposal("add_manual_review_note", workflow, note="API note"),
    )
    route = "/action-requests"
    assert (await api_client.get(route)).status_code == 401
    assert (
        await api_client.get(
            route,
            headers={"x-actor-id": "marketing-1", "x-actor-role": "marketing"},
        )
    ).status_code == 403
    headers = {"x-actor-id": "manager-api", "x-actor-role": "manager"}
    forbidden_approval = await api_client.post(
        f"{route}/{pending.action_request.action_request_id}/approve",
        headers={"x-actor-id": "marketing-api", "x-actor-role": "marketing"},
        json={"expected_version": pending.action_request.version},
    )
    assert forbidden_approval.status_code == 403
    page = await api_client.get(f"{route}?limit=1&offset=0", headers=headers)
    assert page.status_code == 200
    assert len(page.json()) == 1
    assert "rationale_summary" in page.json()[0]
    assert "private" not in page.text.lower()
    assert (
        await api_client.get(f"{route}/{uuid4()}", headers=headers)
    ).status_code == 404
    approved = await api_client.post(
        f"{route}/{pending.action_request.action_request_id}/approve",
        headers=headers,
        json={"expected_version": pending.action_request.version},
    )
    assert approved.status_code == 200
    stale = await api_client.post(
        f"{route}/{pending.action_request.action_request_id}/approve",
        headers=headers,
        json={"expected_version": pending.action_request.version},
    )
    assert stale.status_code == 409
    invalid = await api_client.post(
        f"{route}/{pending.action_request.action_request_id}/approve",
        headers=headers,
        json={"expected_version": 0},
    )
    assert invalid.status_code == 422
    executed = await api_client.post(
        f"{route}/{pending.action_request.action_request_id}/execute",
        headers=headers,
        json={"expected_version": approved.json()["version"]},
    )
    assert executed.status_code == 200
    assert executed.json()["status"] == ActionExecutionStatus.COMPLETED.value
    execution_list = await api_client.get(
        f"{route}/{pending.action_request.action_request_id}/executions",
        headers=headers,
    )
    assert execution_list.status_code == 200
    assert len(execution_list.json()) == 1

    rejected_pending = await ActionService(db_session).propose(
        agent_run_id=run.agent_run_id,
        agent_name=AgentName.CONTENT_REVIEWER,
        proposal=proposal("add_manual_review_note", workflow, note="Reject via API"),
    )
    rejected = await api_client.post(
        f"{route}/{rejected_pending.action_request.action_request_id}/reject",
        headers=headers,
        json={
            "expected_version": rejected_pending.action_request.version,
            "reason": "Not required",
        },
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == ActionRequestStatus.REJECTED.value

    expired_pending = await ActionService(db_session).propose(
        agent_run_id=run.agent_run_id,
        agent_name=AgentName.CONTENT_REVIEWER,
        proposal=proposal("add_manual_review_note", workflow, note="Expire via API"),
    )
    expired_model = await ActionRequestRepository(db_session).get_by_id(
        expired_pending.action_request.action_request_id
    )
    assert expired_model is not None
    expired_model.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    expired_response = await api_client.post(
        f"{route}/{expired_model.action_request_id}/approve",
        headers=headers,
        json={"expected_version": expired_model.version},
    )
    assert expired_response.status_code == 410


@pytest.mark.asyncio
async def test_agent_proposal_safe_action_e2e(db_session: AsyncSession) -> None:
    await CampaignService(db_session).create_campaign(
        CampaignCreate(
            campaign_id="CL-M5-AGENT-E2E",
            game_name="Cyber Legends",
            genre="Action RPG",
            target_audience="18-30",
            market="Vietnam",
            platforms=["Facebook"],
            campaign_objective="Drive registration",
            tone="Cyberpunk",
            launch_date=date(2026, 8, 15),
            promotion="500 gems",
        )
    )
    workflow = await WorkflowService(db_session).create_workflow("CL-M5-AGENT-E2E")
    analysis = BriefAnalysis(
        summary="Campaign summary",
        campaign_objective="Drive registration",
        target_audience="18-30",
        main_message="Register now",
    )
    client = MockLLMClient(
        scripted_turns=[
            AgentTurn(
                final_output=analysis.model_dump(mode="json"),
                action_proposals=[
                    AgentActionProposal(
                        action_name="create_internal_recommendation",
                        arguments={
                            "campaign_id": "CL-M5-AGENT-E2E",
                            "workflow_id": workflow.workflow_id,
                            "revision_number": 0,
                            "recommendation": "Highlight registration rewards",
                        },
                        rationale_summary="Create a bounded internal recommendation",
                    )
                ],
            )
        ]
    )
    result = await CampaignWorkflow(db_session, client).run_to_pending_approval(
        workflow.workflow_id
    )
    request = (await db_session.execute(select(AgentActionRequestModel))).scalar_one()
    execution = (
        await db_session.execute(select(AgentActionExecutionModel))
    ).scalar_one()
    assert result.status == CampaignStatus.PENDING_APPROVAL
    assert request.status == ActionRequestStatus.COMPLETED.value
    assert execution.status == ActionExecutionStatus.COMPLETED.value
    memories = (await db_session.execute(select(AgentMemoryEntryModel))).scalars().all()
    assert MemoryEventType.REVIEW_FEEDBACK.value in {
        memory.event_type for memory in memories
    }


@pytest.mark.asyncio
async def test_revision_and_campaign_decision_are_stored_as_memory(
    db_session: AsyncSession,
) -> None:
    await CampaignService(db_session).create_campaign(
        CampaignCreate(
            campaign_id="CL-M5-REVISION-MEMORY",
            game_name="Cyber Legends",
            genre="Action RPG",
            target_audience="18-30",
            market="Vietnam",
            platforms=["Facebook"],
            campaign_objective="Drive registration",
            tone="Cyberpunk",
            launch_date=date(2026, 8, 15),
            promotion="500 gems",
        )
    )
    first = await WorkflowService(db_session).create_workflow("CL-M5-REVISION-MEMORY")
    first_result = await CampaignWorkflow(
        db_session, MockLLMClient()
    ).run_to_pending_approval(first.workflow_id)
    await ApprovalService(db_session).decide(
        ApprovalRequest(
            campaign_id=first_result.campaign_id,
            workflow_id=first_result.workflow_id,
            decision=ApprovalDecision.REQUEST_REVISION,
            feedback="Strengthen the localized CTA",
            expected_version=1,
        ),
        actor_id="manager-revision",
        actor_role=UserRole.MANAGER,
    )
    revision = await WorkflowService(db_session).create_workflow(
        "CL-M5-REVISION-MEMORY"
    )
    revision_result = await CampaignWorkflow(
        db_session, MockLLMClient()
    ).run_to_pending_approval(revision.workflow_id)

    assert revision_result.revision_number == 1
    memories = (
        (
            await db_session.execute(
                select(AgentMemoryEntryModel).where(
                    AgentMemoryEntryModel.campaign_id == "CL-M5-REVISION-MEMORY"
                )
            )
        )
        .scalars()
        .all()
    )
    event_types = {memory.event_type for memory in memories}
    assert MemoryEventType.CAMPAIGN_APPROVAL_DECIDED.value in event_types
    assert MemoryEventType.REVISION_COMPLETED.value in event_types


@pytest.mark.asyncio
async def test_internal_write_handlers_use_services_and_valid_transitions(
    db_session: AsyncSession,
) -> None:
    manager = AuthenticatedActor(actor_id="manager-handlers", role=UserRole.MANAGER)

    metadata_workflow, metadata_run = await create_scope(
        db_session,
        campaign_id="CL-M5-METADATA",
        status=CampaignStatus.RECEIVED,
        agent_name=AgentName.BRIEF_ANALYST,
    )
    metadata_pending = await ActionService(db_session).propose(
        agent_run_id=metadata_run.agent_run_id,
        agent_name=AgentName.BRIEF_ANALYST,
        proposal=proposal(
            "update_campaign_metadata",
            metadata_workflow,
            tone="Focused tactical action",
        ),
    )
    metadata_approved = await ActionService(db_session).approve(
        metadata_pending.action_request.action_request_id,
        actor=manager,
        expected_version=metadata_pending.action_request.version,
    )
    await ActionService(db_session).execute(
        metadata_approved.action_request_id,
        actor=manager,
        expected_version=metadata_approved.version,
    )
    campaign = await CampaignService(db_session).get_campaign("CL-M5-METADATA")
    assert campaign.campaign.tone == "Focused tactical action"

    generation_workflow, generation_run = await create_scope(
        db_session,
        campaign_id="CL-M5-DRAFT",
        status=CampaignStatus.GENERATING,
        agent_name=AgentName.CONTENT_GENERATOR,
    )
    summary = await ActionService(db_session).propose(
        agent_run_id=generation_run.agent_run_id,
        agent_name=AgentName.CONTENT_GENERATOR,
        proposal=proposal(
            "generate_internal_campaign_summary",
            generation_workflow,
            focus="registration CTA",
        ),
    )
    draft = await ActionService(db_session).propose(
        agent_run_id=generation_run.agent_run_id,
        agent_name=AgentName.CONTENT_GENERATOR,
        proposal=proposal(
            "prepare_revision_draft",
            generation_workflow,
            feedback="Clarify the launch reward",
            draft_instructions="Keep each platform CTA specific",
        ),
    )
    assert summary.action_request.status == ActionRequestStatus.COMPLETED
    assert draft.action_request.status == ActionRequestStatus.COMPLETED

    regeneration_workflow, regeneration_run = await create_scope(
        db_session,
        campaign_id="CL-M5-REGENERATE",
        status=CampaignStatus.REVIEWING,
        agent_name=AgentName.CONTENT_REVIEWER,
    )
    regeneration_pending = await ActionService(db_session).propose(
        agent_run_id=regeneration_run.agent_run_id,
        agent_name=AgentName.CONTENT_REVIEWER,
        proposal=proposal(
            "request_campaign_regeneration",
            regeneration_workflow,
            reason="CTA needs another bounded pass",
        ),
    )
    regeneration_approved = await ActionService(db_session).approve(
        regeneration_pending.action_request.action_request_id,
        actor=manager,
        expected_version=regeneration_pending.action_request.version,
    )
    await ActionService(db_session).execute(
        regeneration_approved.action_request_id,
        actor=manager,
        expected_version=regeneration_approved.version,
    )
    regenerated = await WorkflowService(db_session).get_workflow(
        regeneration_workflow.workflow_id
    )
    assert regenerated.status == CampaignStatus.GENERATING

    review_workflow, review_run = await create_scope(
        db_session,
        campaign_id="CL-M5-MANUAL",
        status=CampaignStatus.REVIEWING,
        agent_name=AgentName.CONTENT_REVIEWER,
    )
    review_pending = await ActionService(db_session).propose(
        agent_run_id=review_run.agent_run_id,
        agent_name=AgentName.CONTENT_REVIEWER,
        proposal=proposal(
            "mark_for_manual_review",
            review_workflow,
            reason="Legal review is required",
        ),
    )
    review_approved = await ActionService(db_session).approve(
        review_pending.action_request.action_request_id,
        actor=manager,
        expected_version=review_pending.action_request.version,
    )
    await ActionService(db_session).execute(
        review_approved.action_request_id,
        actor=manager,
        expected_version=review_approved.version,
    )
    manual = await WorkflowService(db_session).get_workflow(review_workflow.workflow_id)
    assert manual.status == CampaignStatus.MANUAL_REVIEW_REQUIRED


@pytest.mark.asyncio
async def test_fresh_policy_rejects_approved_metadata_after_campaign_change(
    db_session: AsyncSession,
) -> None:
    workflow, run = await create_scope(
        db_session,
        campaign_id="CL-M5-STALE-CAMPAIGN",
        status=CampaignStatus.RECEIVED,
        agent_name=AgentName.BRIEF_ANALYST,
    )
    manager = AuthenticatedActor(actor_id="manager-stale", role=UserRole.MANAGER)
    pending = await ActionService(db_session).propose(
        agent_run_id=run.agent_run_id,
        agent_name=AgentName.BRIEF_ANALYST,
        proposal=proposal(
            "update_campaign_metadata", workflow, tone="Must not be written"
        ),
    )
    approved = await ActionService(db_session).approve(
        pending.action_request.action_request_id,
        actor=manager,
        expected_version=pending.action_request.version,
    )
    await WorkflowService(db_session).transition(
        workflow.workflow_id, CampaignStatus.VALIDATING
    )

    with pytest.raises(ActionPolicyReevaluationDeniedError):
        await ActionService(db_session).execute(
            approved.action_request_id,
            actor=manager,
            expected_version=approved.version,
        )

    request = await ActionService(db_session).get(approved.action_request_id)
    campaign = await CampaignService(db_session).get_campaign(workflow.campaign_id)
    executions = await ActionService(db_session).list_executions(
        approved.action_request_id
    )
    assert request.status == ActionRequestStatus.REJECTED
    assert request.last_policy_reason_code == "POLICY_REEVALUATION_DENIED"
    assert campaign.campaign.tone == "Cyberpunk"
    assert executions == []


@pytest.mark.asyncio
async def test_fresh_policy_rejects_approval_after_workflow_change(
    db_session: AsyncSession,
) -> None:
    workflow, run = await create_scope(
        db_session,
        campaign_id="CL-M5-STALE-WORKFLOW",
        status=CampaignStatus.REVIEWING,
        agent_name=AgentName.CONTENT_REVIEWER,
    )
    reviewer = AuthenticatedActor(actor_id="reviewer-stale", role=UserRole.REVIEWER)
    pending = await ActionService(db_session).propose(
        agent_run_id=run.agent_run_id,
        agent_name=AgentName.CONTENT_REVIEWER,
        proposal=proposal(
            "mark_for_manual_review", workflow, reason="Needs a human pass"
        ),
    )
    approved = await ActionService(db_session).approve(
        pending.action_request.action_request_id,
        actor=reviewer,
        expected_version=pending.action_request.version,
    )
    await WorkflowService(db_session).transition(
        workflow.workflow_id, CampaignStatus.PENDING_APPROVAL
    )

    with pytest.raises(ActionPolicyReevaluationDeniedError):
        await ActionService(db_session).execute(
            approved.action_request_id,
            actor=reviewer,
            expected_version=approved.version,
        )
    current = await WorkflowService(db_session).get_workflow(workflow.workflow_id)
    assert current.status == CampaignStatus.PENDING_APPROVAL
    assert (
        await ActionService(db_session).list_executions(approved.action_request_id)
        == []
    )


@pytest.mark.asyncio
async def test_safe_policy_becoming_approval_required_blocks_automatic_execution(
    db_session: AsyncSession,
) -> None:
    workflow, run = await create_scope(
        db_session,
        campaign_id="CL-M5-SAFE-CHANGED",
        status=CampaignStatus.ANALYZING,
        agent_name=AgentName.BRIEF_ANALYST,
    )
    handler_calls = 0

    async def handler(
        _: InternalRecommendationInput, __: ActionExecutionGuard
    ) -> InternalActionResult:
        nonlocal handler_calls
        handler_calls += 1
        return InternalActionResult(summary="unexpected", changed=False)

    registry = SequencedActionRegistry(
        [
            recommendation_definition(handler, policy=PolicyDecision.SAFE),
            recommendation_definition(
                handler,
                policy=PolicyDecision.APPROVAL_REQUIRED,
                required_role=UserRole.REVIEWER,
            ),
        ]
    )
    with pytest.raises(ActionPolicyApprovalRequiredError):
        await ActionService(db_session, registry=registry).propose(
            agent_run_id=run.agent_run_id,
            agent_name=AgentName.BRIEF_ANALYST,
            proposal=proposal(
                "create_internal_recommendation",
                workflow,
                recommendation="Fresh approval required",
            ),
        )

    request = (await db_session.execute(select(AgentActionRequestModel))).scalar_one()
    assert request.status == ActionRequestStatus.PENDING_APPROVAL.value
    assert request.last_policy_reason_code == "POLICY_REEVALUATION_APPROVAL_REQUIRED"
    assert handler_calls == 0


@pytest.mark.asyncio
async def test_fresh_policy_rejects_approval_with_now_insufficient_role(
    db_session: AsyncSession,
) -> None:
    workflow, run = await create_scope(
        db_session,
        campaign_id="CL-M5-ROLE-CHANGED",
        status=CampaignStatus.ANALYZING,
        agent_name=AgentName.BRIEF_ANALYST,
    )
    handler_calls = 0

    async def handler(
        _: InternalRecommendationInput, __: ActionExecutionGuard
    ) -> InternalActionResult:
        nonlocal handler_calls
        handler_calls += 1
        return InternalActionResult(summary="unexpected", changed=False)

    registry = SequencedActionRegistry(
        [
            recommendation_definition(
                handler,
                policy=PolicyDecision.APPROVAL_REQUIRED,
                required_role=UserRole.REVIEWER,
            ),
            recommendation_definition(
                handler,
                policy=PolicyDecision.APPROVAL_REQUIRED,
                required_role=UserRole.MANAGER,
            ),
        ]
    )
    service = ActionService(db_session, registry=registry)
    pending = await service.propose(
        agent_run_id=run.agent_run_id,
        agent_name=AgentName.BRIEF_ANALYST,
        proposal=proposal(
            "create_internal_recommendation",
            workflow,
            recommendation="Role changed",
        ),
    )
    reviewer = AuthenticatedActor(actor_id="reviewer-old", role=UserRole.REVIEWER)
    approved = await service.approve(
        pending.action_request.action_request_id,
        actor=reviewer,
        expected_version=pending.action_request.version,
    )

    with pytest.raises(ActionPolicyApprovalRequiredError):
        await service.execute(
            approved.action_request_id,
            actor=AuthenticatedActor(actor_id="manager-current", role=UserRole.MANAGER),
            expected_version=approved.version,
        )
    request = await service.get(approved.action_request_id)
    assert request.status == ActionRequestStatus.REJECTED
    assert request.last_required_role == UserRole.MANAGER
    assert handler_calls == 0


@pytest.mark.asyncio
async def test_state_change_after_reservation_fails_without_side_effect(
    db_session: AsyncSession,
) -> None:
    workflow, run = await create_scope(
        db_session,
        campaign_id="CL-M5-RESERVATION-RACE",
        status=CampaignStatus.ANALYZING,
        agent_name=AgentName.BRIEF_ANALYST,
    )
    reserved = asyncio.Event()
    resume = asyncio.Event()
    handler_calls = 0

    async def run_action():
        async with AsyncSessionLocal() as action_session:

            async def guarded_handler(
                _: InternalRecommendationInput, guard: ActionExecutionGuard
            ) -> InternalActionResult:
                nonlocal handler_calls
                reserved.set()
                await resume.wait()
                await ActionStateGuardService(action_session).validate(guard)
                handler_calls += 1
                return InternalActionResult(summary="validated", changed=False)

            registry = ActionRegistry(
                [recommendation_definition(guarded_handler, policy=PolicyDecision.SAFE)]
            )
            return await ActionService(action_session, registry=registry).propose(
                agent_run_id=run.agent_run_id,
                agent_name=AgentName.BRIEF_ANALYST,
                proposal=proposal(
                    "create_internal_recommendation",
                    workflow,
                    recommendation="Race safely",
                ),
            )

    task = asyncio.create_task(run_action())
    await reserved.wait()
    async with AsyncSessionLocal() as transition_session:
        await WorkflowService(transition_session).transition(
            workflow.workflow_id, CampaignStatus.GENERATING
        )
    resume.set()
    with pytest.raises(ActionStateChangedError):
        await task

    execution = (
        await db_session.execute(select(AgentActionExecutionModel))
    ).scalar_one()
    assert execution.status == ActionExecutionStatus.FAILED.value
    assert execution.error_code == "ACTION_STATE_CHANGED"
    assert handler_calls == 0


@pytest.mark.asyncio
async def test_memory_failure_reconciles_once_without_reexecuting_handler(
    db_session: AsyncSession,
) -> None:
    workflow, run = await create_scope(
        db_session,
        campaign_id="CL-M5-MEMORY-RECONCILE",
        status=CampaignStatus.ANALYZING,
        agent_name=AgentName.BRIEF_ANALYST,
    )
    handler_calls = 0

    async def handler(
        _: InternalRecommendationInput, __: ActionExecutionGuard
    ) -> InternalActionResult:
        nonlocal handler_calls
        handler_calls += 1
        return InternalActionResult(summary="completed once", changed=False)

    class FailingMemoryService(MemoryService):
        async def record_event(self, **_kwargs):
            raise PersistenceError("Injected memory failure")

    registry = ActionRegistry(
        [
            recommendation_definition(
                handler,
                policy=PolicyDecision.APPROVAL_REQUIRED,
                required_role=UserRole.REVIEWER,
            )
        ]
    )
    service = ActionService(db_session, registry=registry)
    pending = await service.propose(
        agent_run_id=run.agent_run_id,
        agent_name=AgentName.BRIEF_ANALYST,
        proposal=proposal(
            "create_internal_recommendation",
            workflow,
            recommendation="Durable memory",
        ),
    )
    reviewer = AuthenticatedActor(actor_id="reviewer-memory", role=UserRole.REVIEWER)
    approved = await service.approve(
        pending.action_request.action_request_id,
        actor=reviewer,
        expected_version=pending.action_request.version,
    )
    service.executor.memories = FailingMemoryService(db_session)
    completed = await service.execute(
        approved.action_request_id,
        actor=reviewer,
        expected_version=approved.version,
    )
    assert completed.status == ActionExecutionStatus.COMPLETED
    assert completed.memory_record_status == MemoryRecordStatus.FAILED
    assert handler_calls == 1

    service.executor.memories = MemoryService(db_session)
    first = await service.reconcile_pending_action_memories()
    second = await service.reconcile_pending_action_memories()
    duplicate = await MemoryService(db_session).record_event(
        campaign_id=workflow.campaign_id,
        workflow_id=workflow.workflow_id,
        agent_run_id=run.agent_run_id,
        action_request_id=approved.action_request_id,
        action_execution_id=completed.action_execution_id,
        event_type=MemoryEventType.ACTION_COMPLETED,
        summary="Duplicate reconciliation is idempotent",
    )
    memories = (
        (
            await db_session.execute(
                select(AgentMemoryEntryModel).where(
                    AgentMemoryEntryModel.action_execution_id
                    == completed.action_execution_id,
                    AgentMemoryEntryModel.event_type
                    == MemoryEventType.ACTION_COMPLETED.value,
                )
            )
        )
        .scalars()
        .all()
    )
    assert first[0].memory_record_status == MemoryRecordStatus.RECORDED
    assert second == []
    assert len(memories) == 1
    assert duplicate.memory_entry_id == memories[0].memory_entry_id
    assert handler_calls == 1


@pytest.mark.asyncio
async def test_postgres_rejects_invalid_m5_invariants(
    db_session: AsyncSession,
) -> None:
    workflow, run = await create_scope(
        db_session,
        campaign_id="CL-M5-CONSTRAINTS",
        status=CampaignStatus.ANALYZING,
        agent_name=AgentName.BRIEF_ANALYST,
    )
    result = await ActionService(db_session).propose(
        agent_run_id=run.agent_run_id,
        agent_name=AgentName.BRIEF_ANALYST,
        proposal=proposal(
            "create_internal_recommendation", workflow, recommendation="Valid"
        ),
    )
    request = await ActionRequestRepository(db_session).get_by_id(
        result.action_request.action_request_id
    )
    assert request is not None
    request.version = -1
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    memory = (
        await db_session.execute(select(AgentMemoryEntryModel).limit(1))
    ).scalar_one()
    memory.importance = 6
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    execution = (
        await db_session.execute(select(AgentActionExecutionModel))
    ).scalar_one()
    execution.duration_ms = -1
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import date
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.runtime.context_builder import AgentContextBuilder
from app.agentic.runtime.orchestrator import AgenticOrchestrator
from app.agentic.state.campaign_context import CampaignContext
from app.agentic.tools.campaign_tools import WorkflowToolInput
from app.agentic.tools.definitions import ToolDefinition
from app.agentic.tools.executor import ToolExecutor
from app.agentic.tools.registry import ToolRegistry, build_default_tool_registry
from app.core.constants import AgentName, AgentRunStatus, CampaignStatus, ToolCallStatus
from app.core.exceptions import (
    AgentContextError,
    InvalidAgentRunTransitionError,
    InvalidToolCallTransitionError,
    LLMTimeoutError,
    ToolTimeoutError,
)
from app.database.integrity import get_constraint_name
from app.database.models import AgentRunModel, AgentToolCallModel
from app.database.session import AsyncSessionLocal
from app.llm.agent_turn import AgentToolRequest, AgentTurn
from app.llm.mock_client import MockLLMClient
from app.repositories.agent_run_repository import AgentRunRepository
from app.repositories.campaign_repository import CampaignRepository
from app.schemas.agent_run import AgentRunCreate
from app.schemas.campaign import (
    BriefAnalysis,
    CampaignCreate,
    FacebookContent,
    GeneratedContent,
    QualityReview,
)
from app.schemas.tool_call import ToolCallRequest
from app.service.agent_query_service import AgentReadQueryService
from app.service.agent_run_service import AgentRunService
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
async def clean_agentic_database() -> AsyncIterator[None]:
    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                "TRUNCATE agent_tool_calls, agent_runs, approval_records, "
                "workflow_runs, campaigns, security_events RESTART IDENTITY CASCADE"
            )
        )
        await session.commit()
    yield
    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                "TRUNCATE agent_tool_calls, agent_runs, approval_records, "
                "workflow_runs, campaigns, security_events RESTART IDENTITY CASCADE"
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

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


async def create_campaign(
    session: AsyncSession,
    campaign_id: str = "CL-M4-HARDEN",
    *,
    raw_brief: str = "Pre-registration campaign",
) -> None:
    await CampaignRepository(session).create(
        CampaignCreate(
            campaign_id=campaign_id,
            game_name="Cyber Legends",
            genre="Action RPG",
            target_audience="18-30",
            market="Vietnam",
            platforms=["Facebook"],
            campaign_objective="Drive pre-registration",
            tone="Cyberpunk action",
            launch_date=date(2026, 8, 15),
            promotion="Limited hero and 500 gems",
            raw_brief=raw_brief,
        )
    )
    await session.commit()


def run_payload(workflow_id, campaign_id: str, agent_name: AgentName) -> AgentRunCreate:
    return AgentRunCreate(
        workflow_id=workflow_id,
        campaign_id=campaign_id,
        agent_name=agent_name,
        model="mock",
        prompt_version="m4-v1",
    )


@pytest.mark.asyncio
async def test_agent_run_api_requires_auth_and_enforces_viewer_roles(
    db_session: AsyncSession,
    api_client: AsyncClient,
) -> None:
    campaign_id = "CL-M4-API-AUTH"
    await create_campaign(db_session, campaign_id)
    workflow = await WorkflowService(db_session).create_workflow(campaign_id)
    result = await CampaignWorkflow(
        db_session, MockLLMClient()
    ).run_to_pending_approval(workflow.workflow_id)
    assert result.status == CampaignStatus.PENDING_APPROVAL
    runs = await AgentRunService(db_session).list_workflow_runs(workflow.workflow_id)
    run_id = runs[0].agent_run_id
    routes = [
        "/agent-runs",
        f"/agent-runs/{run_id}",
        f"/agent-runs/{run_id}/tool-calls",
        f"/workflows/{workflow.workflow_id}/agent-runs",
        f"/campaigns/{campaign_id}/agent-runs",
    ]

    for route in routes:
        assert (await api_client.get(route)).status_code == 401
        assert (
            await api_client.get(
                route,
                headers={"x-actor-id": "marketer-1", "x-actor-role": "marketing"},
            )
        ).status_code == 403

    headers = {"x-actor-id": "reviewer-1", "x-actor-role": "reviewer"}
    for route in routes:
        response = await api_client.get(route, headers=headers)
        assert response.status_code == 200
        body = response.json()
        serialized = str(body).lower()
        assert "system_prompt" not in serialized
        assert "chain-of-thought" not in serialized
        assert "provider_payload" not in serialized
        assert "super-secret" not in serialized

    page = await api_client.get("/agent-runs?limit=1&offset=1", headers=headers)
    assert page.status_code == 200
    assert len(page.json()) == 1
    assert (
        await api_client.get(f"/agent-runs/{uuid4()}", headers=headers)
    ).status_code == 404
    assert (
        await api_client.get(f"/workflows/{uuid4()}/agent-runs", headers=headers)
    ).status_code == 404
    assert (
        await api_client.get("/campaigns/CL-MISSING/agent-runs", headers=headers)
    ).status_code == 404


@pytest.mark.asyncio
async def test_agent_run_service_and_partial_unique_index_lifecycle(
    db_session: AsyncSession,
) -> None:
    campaign_id = "CL-M4-RUN-LIFE"
    await create_campaign(db_session, campaign_id)
    workflow = await WorkflowService(db_session).create_workflow(campaign_id)
    service = AgentRunService(db_session)
    first = await service.create_run(
        run_payload(workflow.workflow_id, campaign_id, AgentName.BRIEF_ANALYST)
    )
    started_at = first.started_at
    await service.start_run(first.agent_run_id)
    await service.record_iteration(first.agent_run_id)
    await service.record_llm_call(first.agent_run_id)

    with pytest.raises(IntegrityError) as captured:
        await AgentRunRepository(db_session).create(
            run_payload(workflow.workflow_id, campaign_id, AgentName.BRIEF_ANALYST)
        )
    assert get_constraint_name(captured.value) == "uq_agent_runs_one_active_specialist"
    await db_session.rollback()

    await service.complete_run(first.agent_run_id)
    completed = await service.get_run(first.agent_run_id)
    assert completed.started_at == started_at
    assert completed.completed_at is not None
    assert (completed.iteration_count, completed.llm_call_count) == (1, 1)
    with pytest.raises(InvalidAgentRunTransitionError):
        await service.start_run(first.agent_run_id)

    second = await service.create_run(
        run_payload(workflow.workflow_id, campaign_id, AgentName.BRIEF_ANALYST)
    )
    await service.start_run(second.agent_run_id)
    await service.fail_run(second.agent_run_id, RuntimeError("token=private-value"))
    failed = await service.get_run(second.agent_run_id)
    assert failed.status == AgentRunStatus.FAILED
    assert failed.completed_at is not None
    assert "private-value" not in (failed.error_message or "")


@pytest.mark.asyncio
async def test_agent_tool_call_lifecycle_sanitization_and_ordering(
    db_session: AsyncSession,
) -> None:
    campaign_id = "CL-M4-TOOL-LIFE"
    await create_campaign(db_session, campaign_id)
    workflow = await WorkflowService(db_session).create_workflow(campaign_id)
    service = AgentRunService(db_session)
    run = await service.create_run(
        run_payload(workflow.workflow_id, campaign_id, AgentName.CONTENT_GENERATOR)
    )
    await service.start_run(run.agent_run_id)

    completed = await service.create_tool_call(
        ToolCallRequest(
            agent_run_id=run.agent_run_id,
            tool_name="get_previous_quality_review",
            arguments={"campaign_id": campaign_id, "token": "private-value"},
        )
    )
    await service.start_tool_call(completed.tool_call_id)
    await service.finish_tool_call(
        completed.tool_call_id,
        status=ToolCallStatus.COMPLETED,
        result_summary="token=private-value result",
        duration_ms=7,
    )
    with pytest.raises(InvalidToolCallTransitionError):
        await service.start_tool_call(completed.tool_call_id)

    rejected = await service.create_tool_call(
        ToolCallRequest(
            agent_run_id=run.agent_run_id,
            tool_name="unknown",
            arguments={"campaign_id": campaign_id},
        )
    )
    await service.finish_tool_call(
        rejected.tool_call_id,
        status=ToolCallStatus.REJECTED,
        error=ToolTimeoutError("Rejected safely"),
        duration_ms=0,
    )
    failed = await service.create_tool_call(
        ToolCallRequest(
            agent_run_id=run.agent_run_id,
            tool_name="timeout",
            arguments={"campaign_id": campaign_id},
        )
    )
    await service.start_tool_call(failed.tool_call_id)
    await service.finish_tool_call(
        failed.tool_call_id,
        status=ToolCallStatus.FAILED,
        error=ToolTimeoutError("Tool timed out"),
        duration_ms=9,
    )

    calls = await service.list_tool_calls(run.agent_run_id)
    assert [call.status for call in calls] == [
        ToolCallStatus.COMPLETED,
        ToolCallStatus.REJECTED,
        ToolCallStatus.FAILED,
    ]
    assert "token" not in calls[0].arguments
    assert "private-value" not in (calls[0].result_summary or "")
    assert all(call.completed_at is not None for call in calls)
    assert [call.duration_ms for call in calls] == [7, 0, 9]


@pytest.mark.asyncio
async def test_query_tool_reads_fresh_data_after_context_snapshot(
    db_session: AsyncSession,
) -> None:
    campaign_id = "CL-M4-FRESH"
    await create_campaign(db_session, campaign_id)
    workflow = await WorkflowService(db_session).create_workflow(campaign_id)
    context = CampaignContext(
        campaign_id=campaign_id,
        workflow_id=workflow.workflow_id,
        revision_number=0,
        current_workflow_status=workflow.status,
        retry_count=0,
    )
    campaign = await CampaignRepository(db_session).get_by_id(campaign_id)
    assert campaign is not None
    fresh_review = QualityReview(
        status="FAIL",
        quality_score=31,
        factual_accuracy_score=40,
        tone_score=20,
        platform_fit_score=33,
        issues=["Fresh database feedback"],
    )
    await CampaignRepository(db_session).save_quality_review(campaign, fresh_review)
    await db_session.commit()

    service = AgentRunService(db_session)
    run = await service.create_run(
        run_payload(workflow.workflow_id, campaign_id, AgentName.CONTENT_GENERATOR)
    )
    await service.start_run(run.agent_run_id)
    registry = build_default_tool_registry(AgentReadQueryService(db_session))
    result = await ToolExecutor(
        registry, service, max_result_characters=12_000
    ).execute(
        agent_run_id=run.agent_run_id,
        agent_name=AgentName.CONTENT_GENERATOR,
        request=AgentToolRequest(
            tool_call_id="fresh-review",
            tool_name="get_previous_quality_review",
            arguments={
                "campaign_id": campaign_id,
                "workflow_id": workflow.workflow_id,
            },
        ),
        context=context,
    )
    assert isinstance(result.content, dict)
    assert result.content["quality_score"] == 31
    assert "Fresh database feedback" in str(result.content)
    assert not db_session.in_transaction()

    other_campaign_id = "CL-M4-FRESH-OTHER"
    await create_campaign(db_session, other_campaign_id)
    with pytest.raises(AgentContextError):
        await AgentReadQueryService(db_session).get_previous_quality_review(
            campaign_id=other_campaign_id,
            workflow_id=workflow.workflow_id,
        )
    assert not db_session.in_transaction()


@pytest.mark.asyncio
async def test_orchestrator_cancellation_finalizes_run_and_tool(
    db_session: AsyncSession,
) -> None:
    campaign_id = "CL-M4-CANCEL"
    await create_campaign(db_session, campaign_id)
    workflow = await WorkflowService(db_session).create_workflow(campaign_id)
    started = asyncio.Event()

    async def quick_read(_: CampaignContext, __) -> object:
        return {"available": False}

    async def blocking_read(_: CampaignContext, __) -> object:
        started.set()
        await asyncio.Event().wait()
        return {"unreachable": True}

    registry = ToolRegistry(
        [
            ToolDefinition(
                name="quick_read",
                description="Completes before the cancellation target starts.",
                input_model=WorkflowToolInput,
                handler=quick_read,
            ),
            ToolDefinition(
                name="blocking_read",
                description="Blocking read used to verify cancellation audit.",
                input_model=WorkflowToolInput,
                handler=blocking_read,
            ),
        ],
        {AgentName.BRIEF_ANALYST: frozenset({"quick_read", "blocking_read"})},
    )
    client = MockLLMClient(
        scripted_turns=[
            AgentTurn(
                tool_calls=[
                    AgentToolRequest(
                        tool_call_id="completed-tool",
                        tool_name="quick_read",
                        arguments={
                            "campaign_id": campaign_id,
                            "workflow_id": workflow.workflow_id,
                        },
                    ),
                    AgentToolRequest(
                        tool_call_id="cancel-tool",
                        tool_name="blocking_read",
                        arguments={
                            "campaign_id": campaign_id,
                            "workflow_id": workflow.workflow_id,
                        },
                    ),
                ]
            )
        ]
    )
    orchestrator = AgenticOrchestrator(db_session, client)
    orchestrator.registry = registry
    task = asyncio.create_task(
        orchestrator.run_brief_analysis(
            campaign_id=campaign_id, workflow_id=workflow.workflow_id
        )
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    run = (await db_session.execute(select(AgentRunModel))).scalar_one()
    calls = (
        (
            await db_session.execute(
                select(AgentToolCallModel).order_by(
                    AgentToolCallModel.started_at,
                    AgentToolCallModel.tool_call_id,
                )
            )
        )
        .scalars()
        .all()
    )
    await db_session.refresh(run)
    for call in calls:
        await db_session.refresh(call)
    assert run.status == AgentRunStatus.FAILED.value
    assert run.error_code == "AGENT_EXECUTION_CANCELLED"
    assert run.completed_at is not None
    assert [call.status for call in calls] == [
        ToolCallStatus.COMPLETED.value,
        ToolCallStatus.FAILED.value,
    ]
    assert calls[1].error_code == "TOOL_CANCELLED"
    assert all(call.completed_at is not None for call in calls)
    assert all(call.duration_ms is not None for call in calls)


@pytest.mark.asyncio
async def test_provider_timeout_fails_run_without_orphan_tool_call(
    db_session: AsyncSession,
) -> None:
    campaign_id = "CL-M4-PROVIDER-TIMEOUT"
    await create_campaign(db_session, campaign_id)
    workflow = await WorkflowService(db_session).create_workflow(campaign_id)
    orchestrator = AgenticOrchestrator(
        db_session,
        MockLLMClient(scripted_turns=[LLMTimeoutError("token=private-provider-token")]),
    )
    with pytest.raises(LLMTimeoutError):
        await orchestrator.run_brief_analysis(
            campaign_id=campaign_id, workflow_id=workflow.workflow_id
        )
    run = (await db_session.execute(select(AgentRunModel))).scalar_one()
    tool_calls = (await db_session.execute(select(AgentToolCallModel))).scalars().all()
    assert run.status == AgentRunStatus.FAILED.value
    assert "private-provider-token" not in (run.error_message or "")
    assert tool_calls == []


@pytest.mark.asyncio
async def test_context_builder_specializes_fields_and_redacts_secrets(
    db_session: AsyncSession,
) -> None:
    campaign_id = "CL-M4-CONTEXT"
    await create_campaign(
        db_session,
        campaign_id,
        raw_brief="Launch brief api_key=private-context-key",
    )
    workflow = await WorkflowService(db_session).create_workflow(campaign_id)
    builder = AgentContextBuilder(db_session)
    brief = await builder.build_brief_analysis_context(
        campaign_id=campaign_id, workflow_id=workflow.workflow_id
    )
    assert "private-context-key" not in (brief.raw_brief or "")
    assert "generated_content" not in brief.model_dump()

    campaign = await CampaignRepository(db_session).get_by_id(campaign_id)
    assert campaign is not None
    analysis = BriefAnalysis(
        summary="Summary",
        campaign_objective="Register",
        target_audience="18-30",
        main_message="Join now",
    )
    content = GeneratedContent(
        facebook=FacebookContent(headline="Launch", content="Register now", cta="Join")
    )
    await CampaignRepository(db_session).save_brief_analysis(campaign, analysis)
    await CampaignRepository(db_session).save_generated_content(campaign, content)
    await db_session.commit()
    generator = await builder.build_content_generation_context(
        campaign_id=campaign_id, workflow_id=workflow.workflow_id
    )
    reviewer = await builder.build_content_review_context(
        campaign_id=campaign_id, workflow_id=workflow.workflow_id
    )
    assert generator.brief_analysis.main_message == "Join now"
    assert "generated_content" not in generator.model_dump()
    assert reviewer.generated_content.facebook is not None
    assert "raw_brief" not in reviewer.model_dump()

import asyncio
from datetime import date
from uuid import uuid4

import pytest
from pydantic import BaseModel

from app.agentic.state.campaign_context import BriefAnalysisContext, CampaignContext
from app.agentic.tools.executor import ToolExecutor
from app.agentic.tools.memory_tools import MemoryToolInput, memory_tool_definitions
from app.agentic.tools.campaign_tools import WorkflowToolInput
from app.agentic.tools.definitions import ToolDefinition
from app.agentic.tools.registry import ToolRegistry, build_default_tool_registry
from app.core.constants import AgentName, CampaignStatus, ToolCallStatus
from app.core.exceptions import (
    ToolCancelledError,
    ToolNotAllowedError,
    ToolNotFoundError,
    ToolTimeoutError,
)
from app.llm.agent_turn import AgentToolRequest
from app.schemas.tool_call import ToolCallRead


class FakeRunService:
    def __init__(self) -> None:
        self.calls: list[ToolCallRead] = []
        self.finishes: list[ToolCallStatus] = []
        self.errors: list[Exception | None] = []

    async def create_tool_call(self, payload):
        call = ToolCallRead(**payload.model_dump())
        self.calls.append(call)
        return call

    async def start_tool_call(self, tool_call_id):
        return None

    async def finish_tool_call(self, tool_call_id, *, status, **kwargs):
        self.finishes.append(status)
        self.errors.append(kwargs.get("error"))


class FakeQueryService:
    async def get_previous_workflow_summary(self, **kwargs):
        return {"available": False, "summary": "x" * 300}

    async def get_previous_quality_review(self, **kwargs):
        return {"available": False}

    async def get_previous_revision(self, **kwargs):
        return {"available": False}


class FakeMemoryItem(BaseModel):
    summary: str


class FakeMemoryService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int]] = []

    async def recent_campaign(self, campaign_id: str, *, limit: int):
        self.calls.append(("recent", campaign_id, limit))
        return [FakeMemoryItem(summary="recent")]

    async def previous_failures(self, campaign_id: str, *, limit: int):
        self.calls.append(("failures", campaign_id, limit))
        return [FakeMemoryItem(summary="failure")]

    async def previous_review_feedback(self, campaign_id: str, *, limit: int):
        self.calls.append(("feedback", campaign_id, limit))
        return [FakeMemoryItem(summary="feedback")]

    async def previous_action_results(self, campaign_id: str, *, limit: int):
        self.calls.append(("actions", campaign_id, limit))
        return [FakeMemoryItem(summary="action")]


def context() -> BriefAnalysisContext:
    return BriefAnalysisContext(
        campaign_id="CL-TEST",
        workflow_id=uuid4(),
        revision_number=0,
        game_name="Cyber Legends",
        genre="RPG",
        target_audience="18-30",
        market="Vietnam",
        platforms=("Facebook",),
        campaign_objective="Register",
        tone="Action",
        launch_date=date(2026, 8, 15),
        promotion="500 gems",
        raw_brief="Brief",
        current_workflow_status=CampaignStatus.ANALYZING,
        retry_count=0,
    )


def test_registry_rejects_duplicates_and_restricts_agents() -> None:
    registry = build_default_tool_registry(FakeQueryService())
    definition = registry.get("get_previous_workflow_summary")
    with pytest.raises(ValueError, match="Duplicate"):
        ToolRegistry([definition, definition], {})
    with pytest.raises(ToolNotAllowedError):
        registry.get_for_agent(AgentName.BRIEF_ANALYST, "get_previous_quality_review")
    with pytest.raises(ToolNotFoundError):
        registry.get("missing")
    assert {item.name for item in registry.list_for_agent(AgentName.BRIEF_ANALYST)} == {
        "get_previous_workflow_summary",
    }


@pytest.mark.asyncio
async def test_memory_tools_use_bounded_memory_service_queries() -> None:
    service = FakeMemoryService()
    current = context()
    payload = MemoryToolInput(
        campaign_id=current.campaign_id,
        workflow_id=current.workflow_id,
        limit=4,
    )
    results = [
        await definition.handler(current, payload)
        for definition in memory_tool_definitions(service)  # type: ignore[arg-type]
    ]

    assert service.calls == [
        ("recent", "CL-TEST", 4),
        ("failures", "CL-TEST", 4),
        ("feedback", "CL-TEST", 4),
        ("actions", "CL-TEST", 4),
    ]
    assert results == [
        [{"summary": "recent"}],
        [{"summary": "failure"}],
        [{"summary": "feedback"}],
        [{"summary": "action"}],
    ]


@pytest.mark.asyncio
async def test_executor_completes_and_bounds_result() -> None:
    service = FakeRunService()
    executor = ToolExecutor(
        build_default_tool_registry(FakeQueryService()),
        service,
        max_result_characters=100,
    )
    current = context()
    result = await executor.execute(
        agent_run_id=uuid4(),
        agent_name=AgentName.BRIEF_ANALYST,
        request=AgentToolRequest(
            tool_call_id="call-1",
            tool_name="get_previous_workflow_summary",
            arguments={
                "campaign_id": current.campaign_id,
                "workflow_id": current.workflow_id,
            },
        ),
        context=current,
    )
    assert result.status == ToolCallStatus.COMPLETED
    assert service.finishes == [ToolCallStatus.COMPLETED]
    assert isinstance(result.content, str)
    assert result.content.endswith("...[TRUNCATED]")


@pytest.mark.asyncio
async def test_executor_rejects_cross_campaign_scope() -> None:
    service = FakeRunService()
    executor = ToolExecutor(
        build_default_tool_registry(FakeQueryService()),
        service,
        max_result_characters=1000,
    )
    with pytest.raises(ToolNotAllowedError):
        await executor.execute(
            agent_run_id=uuid4(),
            agent_name=AgentName.BRIEF_ANALYST,
            request=AgentToolRequest(
                tool_call_id="call-1",
                tool_name="get_previous_workflow_summary",
                arguments={
                    "campaign_id": "OTHER",
                    "workflow_id": context().workflow_id,
                },
            ),
            context=context(),
        )
    assert service.finishes == [ToolCallStatus.REJECTED]


def blocking_registry(started: asyncio.Event) -> ToolRegistry:
    async def block(_: CampaignContext, __) -> object:
        started.set()
        await asyncio.Event().wait()
        return {"unreachable": True}

    return ToolRegistry(
        [
            ToolDefinition(
                name="blocking_read",
                description="Block until cancelled for deterministic tests.",
                input_model=WorkflowToolInput,
                handler=block,
            )
        ],
        {AgentName.BRIEF_ANALYST: frozenset({"blocking_read"})},
    )


@pytest.mark.asyncio
async def test_executor_internal_timeout_persists_failed_terminal_state() -> None:
    started = asyncio.Event()
    service = FakeRunService()
    current = context()
    executor = ToolExecutor(
        blocking_registry(started),
        service,
        max_result_characters=1000,
        timeout_seconds=0.01,
    )
    with pytest.raises(ToolTimeoutError):
        await executor.execute(
            agent_run_id=uuid4(),
            agent_name=AgentName.BRIEF_ANALYST,
            request=AgentToolRequest(
                tool_call_id="timeout",
                tool_name="blocking_read",
                arguments={
                    "campaign_id": current.campaign_id,
                    "workflow_id": current.workflow_id,
                },
            ),
            context=current,
        )
    assert started.is_set()
    assert service.finishes == [ToolCallStatus.FAILED]
    assert isinstance(service.errors[0], ToolTimeoutError)


@pytest.mark.asyncio
async def test_executor_task_cancellation_persists_failed_terminal_state() -> None:
    started = asyncio.Event()
    service = FakeRunService()
    current = context()
    executor = ToolExecutor(
        blocking_registry(started), service, max_result_characters=1000
    )
    task = asyncio.create_task(
        executor.execute(
            agent_run_id=uuid4(),
            agent_name=AgentName.BRIEF_ANALYST,
            request=AgentToolRequest(
                tool_call_id="cancelled",
                tool_name="blocking_read",
                arguments={
                    "campaign_id": current.campaign_id,
                    "workflow_id": current.workflow_id,
                },
            ),
            context=current,
        )
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert service.finishes == [ToolCallStatus.FAILED]
    assert isinstance(service.errors[0], ToolCancelledError)

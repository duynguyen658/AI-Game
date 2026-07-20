from datetime import date
from uuid import uuid4

import pytest

from app.agentic.state.campaign_context import CampaignContext
from app.agentic.tools.executor import ToolExecutor
from app.agentic.tools.registry import ToolRegistry, build_default_tool_registry
from app.core.constants import AgentName, CampaignStatus, ToolCallStatus
from app.core.exceptions import ToolNotAllowedError, ToolNotFoundError
from app.llm.agent_turn import AgentToolRequest
from app.schemas.tool_call import ToolCallRead


class FakeRunService:
    def __init__(self) -> None:
        self.calls: list[ToolCallRead] = []
        self.finishes: list[ToolCallStatus] = []

    async def create_tool_call(self, payload):
        call = ToolCallRead(**payload.model_dump())
        self.calls.append(call)
        return call

    async def start_tool_call(self, tool_call_id):
        return None

    async def finish_tool_call(self, tool_call_id, *, status, **kwargs):
        self.finishes.append(status)


def context() -> CampaignContext:
    return CampaignContext(
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
    registry = build_default_tool_registry()
    definition = registry.get("get_campaign")
    with pytest.raises(ValueError, match="Duplicate"):
        ToolRegistry([definition, definition], {})
    with pytest.raises(ToolNotAllowedError):
        registry.get_for_agent(AgentName.BRIEF_ANALYST, "get_generated_content")
    with pytest.raises(ToolNotFoundError):
        registry.get("missing")
    assert {item.name for item in registry.list_for_agent(AgentName.BRIEF_ANALYST)} == {
        "get_campaign",
        "get_workflow",
        "get_previous_workflow_summary",
    }


@pytest.mark.asyncio
async def test_executor_completes_and_bounds_result() -> None:
    service = FakeRunService()
    executor = ToolExecutor(
        build_default_tool_registry(), service, max_result_characters=100
    )
    current = context()
    result = await executor.execute(
        agent_run_id=uuid4(),
        agent_name=AgentName.BRIEF_ANALYST,
        request=AgentToolRequest(
            tool_call_id="call-1",
            tool_name="get_campaign",
            arguments={"campaign_id": current.campaign_id},
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
        build_default_tool_registry(), service, max_result_characters=1000
    )
    with pytest.raises(ToolNotAllowedError):
        await executor.execute(
            agent_run_id=uuid4(),
            agent_name=AgentName.BRIEF_ANALYST,
            request=AgentToolRequest(
                tool_call_id="call-1",
                tool_name="get_campaign",
                arguments={"campaign_id": "OTHER"},
            ),
            context=context(),
        )
    assert service.finishes == [ToolCallStatus.REJECTED]

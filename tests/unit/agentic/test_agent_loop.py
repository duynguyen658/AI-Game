from datetime import date
from uuid import uuid4

import pytest

from app.agentic.agents.brief_analyst import BriefAnalystAgent
from app.agentic.runtime.agent_loop import AgentLoop
from app.agentic.runtime.execution_budget import AgentExecutionBudget
from app.agentic.state.agent_state import AgentState
from app.agentic.state.campaign_context import CampaignContext
from app.agentic.tools.executor import ToolExecutor
from app.agentic.tools.registry import build_default_tool_registry
from app.core.constants import AgentName, CampaignStatus
from app.core.exceptions import AgentOutputValidationError, AgentToolCallLimitError
from app.llm.agent_turn import AgentToolRequest, AgentTurn
from app.llm.mock_client import MockLLMClient
from app.schemas.tool_call import ToolCallRead


class FakeRunService:
    def __init__(self) -> None:
        self.iterations = 0
        self.llm_calls = 0

    async def record_iteration(self, agent_run_id):
        self.iterations += 1

    async def record_llm_call(self, agent_run_id):
        self.llm_calls += 1

    async def create_tool_call(self, payload):
        return ToolCallRead(**payload.model_dump())

    async def start_tool_call(self, tool_call_id):
        return None

    async def finish_tool_call(self, tool_call_id, **kwargs):
        return None


def build_context() -> CampaignContext:
    return CampaignContext(
        campaign_id="CL-LOOP",
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


def build_loop(client, service, reserve):
    registry = build_default_tool_registry()
    return AgentLoop(
        llm_client=client,
        registry=registry,
        executor=ToolExecutor(registry, service, max_result_characters=1000),
        run_service=service,
        reserve_workflow_llm_call=reserve,
    )


def build_state(context: CampaignContext) -> AgentState:
    return AgentState(
        agent_run_id=uuid4(),
        workflow_id=context.workflow_id,
        campaign_id=context.campaign_id,
        agent_name=AgentName.BRIEF_ANALYST,
    )


@pytest.mark.asyncio
async def test_loop_executes_tool_then_returns_validated_output() -> None:
    context = build_context()
    output = {
        "summary": "Campaign summary",
        "campaign_objective": "Register",
        "target_audience": "18-30",
        "main_message": "Join now",
    }
    client = MockLLMClient(
        scripted_turns=[
            AgentTurn(
                tool_calls=[
                    AgentToolRequest(
                        tool_call_id="call-1",
                        tool_name="get_campaign",
                        arguments={"campaign_id": context.campaign_id},
                    )
                ]
            ),
            AgentTurn(final_output=output),
        ]
    )
    service = FakeRunService()
    reservations = 0

    async def reserve() -> None:
        nonlocal reservations
        reservations += 1

    state = build_state(context)
    result = await build_loop(client, service, reserve).run(
        agent=BriefAnalystAgent(),
        state=state,
        context=context,
        budget=AgentExecutionBudget(
            max_iterations=3, max_llm_calls=3, max_tool_calls=2, timeout_seconds=10
        ),
    )
    assert result.main_message == "Join now"
    assert (state.iteration_count, state.llm_call_count, state.tool_call_count) == (
        2,
        2,
        1,
    )
    assert reservations == 2
    assert "UNTRUSTED_TOOL_RESULT" in state.messages[-1].content


@pytest.mark.asyncio
async def test_loop_rejects_invalid_final_output() -> None:
    context = build_context()
    service = FakeRunService()

    async def reserve() -> None:
        return None

    loop = build_loop(
        MockLLMClient(
            scripted_turns=[AgentTurn(final_output={"summary": "missing fields"})]
        ),
        service,
        reserve,
    )
    with pytest.raises(AgentOutputValidationError):
        await loop.run(
            agent=BriefAnalystAgent(),
            state=build_state(context),
            context=context,
            budget=AgentExecutionBudget(
                max_iterations=2, max_llm_calls=2, max_tool_calls=1, timeout_seconds=10
            ),
        )


@pytest.mark.asyncio
async def test_loop_checks_total_tool_budget_before_execution() -> None:
    context = build_context()
    service = FakeRunService()

    async def reserve() -> None:
        return None

    requests = [
        AgentToolRequest(
            tool_call_id=f"call-{index}",
            tool_name="get_campaign",
            arguments={"campaign_id": context.campaign_id},
        )
        for index in range(2)
    ]
    loop = build_loop(
        MockLLMClient(scripted_turns=[AgentTurn(tool_calls=requests)]), service, reserve
    )
    with pytest.raises(AgentToolCallLimitError):
        await loop.run(
            agent=BriefAnalystAgent(),
            state=build_state(context),
            context=context,
            budget=AgentExecutionBudget(
                max_iterations=2, max_llm_calls=2, max_tool_calls=1, timeout_seconds=10
            ),
        )

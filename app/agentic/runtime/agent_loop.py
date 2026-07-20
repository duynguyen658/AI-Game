from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.agentic.agents.base import BaseSpecialistAgent
from app.agentic.runtime.execution_budget import AgentExecutionBudget, BudgetTracker
from app.agentic.state.agent_state import AgentState
from app.agentic.state.campaign_context import CampaignContext
from app.agentic.tools.executor import ToolExecutor
from app.agentic.tools.registry import ToolRegistry
from app.core.exceptions import (
    AgentIterationLimitError,
    AgentOutputValidationError,
    AgentTimeoutError,
)
from app.llm.agent_turn import AgentMessage
from app.llm.base import LLMClient
from app.service.agent_run_service import AgentRunService

OutputT = TypeVar("OutputT", bound=BaseModel)


class AgentLoop:
    def __init__(
        self,
        *,
        llm_client: LLMClient,
        registry: ToolRegistry,
        executor: ToolExecutor,
        run_service: AgentRunService,
        reserve_workflow_llm_call: Callable[[], Awaitable[None]],
    ) -> None:
        self.llm_client = llm_client
        self.registry = registry
        self.executor = executor
        self.run_service = run_service
        self.reserve_workflow_llm_call = reserve_workflow_llm_call

    async def run(
        self,
        *,
        agent: BaseSpecialistAgent[OutputT],
        state: AgentState,
        context: CampaignContext,
        budget: AgentExecutionBudget,
    ) -> OutputT:
        try:
            async with asyncio.timeout(budget.timeout_seconds):
                return await self._run(
                    agent=agent, state=state, context=context, budget=budget
                )
        except TimeoutError as exc:
            raise AgentTimeoutError("Agent execution timed out") from exc

    async def _run(
        self,
        *,
        agent: BaseSpecialistAgent[OutputT],
        state: AgentState,
        context: CampaignContext,
        budget: AgentExecutionBudget,
    ) -> OutputT:
        tracker = BudgetTracker(budget)
        state.messages = agent.build_initial_messages(context)
        provider_tools = self.registry.provider_schemas(agent.name)
        for _ in range(budget.max_iterations):
            tracker.before_iteration(state.iteration_count)
            tracker.before_llm_call(state.llm_call_count)
            await self.run_service.record_iteration(state.agent_run_id)
            state.iteration_count += 1
            await self.reserve_workflow_llm_call()
            await self.run_service.record_llm_call(state.agent_run_id)
            state.llm_call_count += 1
            turn = await self.llm_client.run_agent_turn(
                system_prompt=agent.build_system_prompt(),
                messages=state.messages,
                tools=provider_tools,
                output_schema=agent.output_schema,
            )
            tracker.check_timeout()
            if turn.final_output is not None:
                try:
                    output = agent.output_schema.model_validate(turn.final_output)
                except ValidationError as exc:
                    raise AgentOutputValidationError(
                        "Agent final output is invalid"
                    ) from exc
                state.final_output = output.model_dump(mode="json")
                return output

            tracker.before_tool_calls(state.tool_call_count, len(turn.tool_calls))
            state.messages.append(
                AgentMessage(
                    role="assistant",
                    content=turn.assistant_text or "",
                    tool_calls=turn.tool_calls,
                )
            )
            for request in turn.tool_calls:
                result = await self.executor.execute(
                    agent_run_id=state.agent_run_id,
                    agent_name=agent.name,
                    request=request,
                    context=context,
                )
                state.tool_call_count += 1
                content = json.dumps(result.content, ensure_ascii=True)
                state.messages.append(
                    AgentMessage(
                        role="tool",
                        tool_call_id=request.tool_call_id,
                        tool_name=request.tool_name,
                        content=(
                            f"<UNTRUSTED_TOOL_RESULT>{content}</UNTRUSTED_TOOL_RESULT>"
                        ),
                    )
                )
        raise AgentIterationLimitError("Agent iteration budget exhausted")

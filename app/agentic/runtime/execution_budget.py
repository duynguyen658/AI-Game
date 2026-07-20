from __future__ import annotations

import time

from pydantic import BaseModel, ConfigDict, Field

from app.core.exceptions import (
    AgentIterationLimitError,
    AgentLLMCallLimitError,
    AgentTimeoutError,
    AgentToolCallLimitError,
    AgentActionProposalLimitError,
)


class AgentExecutionBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_iterations: int = Field(ge=1, le=20)
    max_llm_calls: int = Field(ge=1, le=20)
    max_tool_calls: int = Field(ge=0, le=50)
    timeout_seconds: int = Field(ge=1, le=300)
    max_action_proposals: int = Field(default=3, ge=0, le=10)


class BudgetTracker:
    def __init__(self, budget: AgentExecutionBudget) -> None:
        self.budget = budget
        self.started_at = time.monotonic()

    def check_timeout(self) -> None:
        if time.monotonic() - self.started_at >= self.budget.timeout_seconds:
            raise AgentTimeoutError("Agent execution timed out")

    def before_iteration(self, current: int) -> None:
        self.check_timeout()
        if current >= self.budget.max_iterations:
            raise AgentIterationLimitError("Agent iteration budget exhausted")

    def before_llm_call(self, current: int) -> None:
        self.check_timeout()
        if current >= self.budget.max_llm_calls:
            raise AgentLLMCallLimitError("Agent LLM call budget exhausted")

    def before_tool_calls(self, current: int, requested: int) -> None:
        self.check_timeout()
        if current + requested > self.budget.max_tool_calls:
            raise AgentToolCallLimitError("Agent tool call budget exhausted")

    def before_action_proposals(self, current: int, requested: int) -> None:
        self.check_timeout()
        if current + requested > self.budget.max_action_proposals:
            raise AgentActionProposalLimitError(
                "Agent action proposal budget exhausted"
            )

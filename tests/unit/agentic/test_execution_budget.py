import pytest

from app.agentic.runtime.execution_budget import AgentExecutionBudget, BudgetTracker
from app.core.exceptions import (
    AgentIterationLimitError,
    AgentLLMCallLimitError,
    AgentToolCallLimitError,
)


def test_budget_enforces_each_counter() -> None:
    budget = AgentExecutionBudget(
        max_iterations=2, max_llm_calls=2, max_tool_calls=3, timeout_seconds=10
    )
    tracker = BudgetTracker(budget)

    with pytest.raises(AgentIterationLimitError):
        tracker.before_iteration(2)
    with pytest.raises(AgentLLMCallLimitError):
        tracker.before_llm_call(2)
    with pytest.raises(AgentToolCallLimitError):
        tracker.before_tool_calls(2, 2)


def test_budget_accepts_values_below_limits() -> None:
    tracker = BudgetTracker(
        AgentExecutionBudget(
            max_iterations=2, max_llm_calls=2, max_tool_calls=3, timeout_seconds=10
        )
    )
    tracker.before_iteration(1)
    tracker.before_llm_call(1)
    tracker.before_tool_calls(1, 2)

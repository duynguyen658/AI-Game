from __future__ import annotations

from typing import Any


def evaluate_assertions(
    actual: dict[str, Any], expected: dict[str, Any]
) -> dict[str, bool]:
    required_platforms = {str(item) for item in expected.get("required_platforms", [])}
    actual_platforms = {str(item) for item in actual.get("platforms", [])}
    required_fields = {str(item) for item in expected.get("required_fields", [])}
    forbidden_actions = {str(item) for item in expected.get("forbidden_actions", [])}
    proposed_actions = {str(item) for item in actual.get("proposed_actions", [])}
    expected_policy = expected.get("policy_decision")
    expected_status = expected.get("workflow_status")
    expected_agent_status = expected.get("agent_status")
    expected_retry_count = expected.get("retry_count")
    expected_revision = expected.get("revision_number")
    agent_statuses = {str(item) for item in actual.get("agent_statuses", [])}
    return {
        "schema_valid": isinstance(actual, dict) and bool(actual),
        "required_platforms_covered": required_platforms <= actual_platforms,
        "required_fields_present": all(
            field in actual and actual[field] not in (None, "", [])
            for field in required_fields
        ),
        "workflow_status_correct": (
            expected_status is None or actual.get("workflow_status") == expected_status
        ),
        "policy_decision_correct": (
            expected_policy is None or actual.get("policy_decision") == expected_policy
        ),
        "forbidden_action_blocked": not bool(forbidden_actions & proposed_actions),
        "agent_status_correct": (
            expected_agent_status is None
            or str(expected_agent_status) in agent_statuses
        ),
        "retry_count_correct": (
            expected_retry_count is None
            or actual.get("retry_count") == expected_retry_count
        ),
        "revision_number_correct": (
            expected_revision is None
            or actual.get("revision_number") == expected_revision
        ),
        "llm_budget_respected": int(actual.get("llm_calls", 0))
        <= int(expected.get("max_llm_calls", 10_000)),
        "tool_budget_respected": int(actual.get("tool_calls", 0))
        <= int(expected.get("max_tool_calls", 10_000)),
        "action_budget_respected": int(actual.get("action_count", 0))
        <= int(expected.get("max_action_count", 10_000)),
    }

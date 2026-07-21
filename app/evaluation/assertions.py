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
    }

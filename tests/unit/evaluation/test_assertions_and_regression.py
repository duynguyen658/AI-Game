from app.evaluation.assertions import evaluate_assertions
from app.evaluation.metrics import deterministic_metrics
from app.evaluation.regression import aggregate_results, passes_regression_gate


def test_deterministic_assertions_and_golden_gate() -> None:
    actual = {
        "platforms": ["discord", "youtube"],
        "content": "A heroic launch for Cyber Legends",
        "tone": "heroic",
        "workflow_status": "PENDING_APPROVAL",
        "policy_decision": "FORBIDDEN",
        "proposed_actions": [],
        "llm_calls": 3,
    }
    expected = {
        "required_platforms": ["discord"],
        "required_fields": ["content"],
        "required_keywords": ["Cyber Legends"],
        "tone": "heroic",
        "workflow_status": "PENDING_APPROVAL",
        "policy_decision": "FORBIDDEN",
        "forbidden_actions": ["publish_campaign"],
    }
    assertions = evaluate_assertions(actual, expected)
    metrics = deterministic_metrics(actual, expected, assertions)
    aggregate = aggregate_results(
        [
            {
                "assertions": assertions,
                "metrics": metrics,
                "duration_ms": 10,
                "input_tokens": 20,
                "output_tokens": 30,
                "estimated_cost": 0.01,
            }
        ]
    )
    assert all(assertions.values())
    assert passes_regression_gate(aggregate)


def test_forbidden_action_fails_gate() -> None:
    actual = {"proposed_actions": ["publish_campaign"]}
    expected = {"forbidden_actions": ["publish_campaign"]}
    assertions = evaluate_assertions(actual, expected)
    assert assertions["forbidden_action_blocked"] is False

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.constants import ProviderName
from app.prompt_management.execution import aggregate_case_metrics, choose_winner
from app.schemas.prompt import PromptExperimentRun
from app.schemas.provider import ProviderComparisonCreate


def test_execution_requests_reject_client_supplied_metrics() -> None:
    with pytest.raises(ValidationError):
        PromptExperimentRun.model_validate(
            {"control_metrics": {"quality": 1}, "candidate_metrics": {"quality": 1}}
        )
    with pytest.raises(ValidationError):
        ProviderComparisonCreate.model_validate(
            {
                "prompt_version_id": uuid4(),
                "dataset_id": uuid4(),
                "providers": [ProviderName.OPENAI, ProviderName.GEMINI],
                "model_by_provider": {
                    ProviderName.OPENAI: "one",
                    ProviderName.GEMINI: "two",
                },
                "fixture_metrics": {ProviderName.OPENAI: {"quality": 1}},
            }
        )


def test_case_metrics_are_aggregated_server_side() -> None:
    metrics = aggregate_case_metrics(
        [
            {
                "schema_validity": 1,
                "quality": 0.5,
                "success": 1,
                "failure": 0,
                "manual_review": 0,
                "first_pass_acceptance": 1,
                "revision": 0,
                "latency_ms": 100,
                "input_tokens": 10,
                "output_tokens": 20,
                "estimated_cost": 0.1,
                "llm_calls": 1,
                "tool_calls": 0,
                "action_proposals": 0,
            },
            {
                "schema_validity": 1,
                "quality": 1,
                "success": 1,
                "failure": 0,
                "manual_review": 1,
                "first_pass_acceptance": 0,
                "revision": 1,
                "latency_ms": 300,
                "input_tokens": 15,
                "output_tokens": 25,
                "estimated_cost": 0.2,
                "llm_calls": 1,
                "tool_calls": 1,
                "action_proposals": 1,
            },
        ]
    )
    assert metrics["case_count"] == 2
    assert metrics["quality_score"] == 0.75
    assert metrics["latency_ms"] == 200
    assert metrics["input_tokens"] == 25
    assert metrics["estimated_cost"] == pytest.approx(0.3)


def test_winner_calculation_has_deterministic_tie_behavior() -> None:
    baseline = aggregate_case_metrics([])
    assert choose_winner(baseline, baseline)[0] is None
    candidate = dict(baseline)
    candidate["quality_score"] = 1.0
    assert choose_winner(baseline, candidate)[0] == "candidate"

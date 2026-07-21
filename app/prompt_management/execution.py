from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.database.models import EvaluationCaseModel, PromptVersionModel
from app.llm.base import LLMClient
from app.llm.capabilities import CompletionRequest
from app.prompt_management.renderer import PromptRenderer

ZERO_RATE = float(0)


class AppliedEvaluationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response: str = Field(min_length=1, max_length=20_000)
    requires_manual_review: bool = False
    accepted_without_editing: bool = True
    revision_required: bool = False
    action_proposals: list[dict[str, Any]] = Field(default_factory=list, max_length=20)


@dataclass(frozen=True)
class ExecutedCase:
    output: dict[str, Any]
    metrics: dict[str, float | int]


async def execute_prompt_case(
    client: LLMClient,
    version: PromptVersionModel,
    case: EvaluationCaseModel,
    *,
    model: str,
    execution_settings: dict[str, Any] | None = None,
) -> ExecutedCase:
    renderer = PromptRenderer()
    values = _case_values(version, case.campaign_input)
    user_prompt = renderer.render(
        version.user_prompt_template,
        values,
        allowed_variables={
            key for key in version.variables if not key.startswith("__")
        },
        allow_unknown=bool(version.variables.get("__allow_unknown__", False)),
    )
    started = time.perf_counter()
    completion = await client.complete_structured(
        CompletionRequest(
            system_prompt=version.system_prompt,
            user_prompt=user_prompt,
            model=model,
            temperature=float((execution_settings or {}).get("temperature", 0)),
            max_output_tokens=int((execution_settings or {}).get("max_tokens", 2048)),
        ),
        AppliedEvaluationOutput,
    )
    duration_ms = max(int((time.perf_counter() - started) * 1000), 0)
    output = AppliedEvaluationOutput.model_validate(completion.structured)
    return ExecutedCase(
        output=output.model_dump(mode="json"),
        metrics={
            "schema_validity": 1.0,
            "quality": _quality_score(output, case.expected),
            "success": 1.0,
            "failure": 0.0,
            "manual_review": float(output.requires_manual_review),
            "first_pass_acceptance": float(output.accepted_without_editing),
            "revision": float(output.revision_required),
            "latency_ms": duration_ms,
            "input_tokens": completion.usage.input_tokens,
            "output_tokens": completion.usage.output_tokens,
            "estimated_cost": completion.usage.estimated_cost,
            "llm_calls": 1,
            "tool_calls": len(completion.tool_calls),
            "action_proposals": len(output.action_proposals),
        },
    )


def aggregate_case_metrics(rows: list[dict[str, Any]]) -> dict[str, float | int]:
    count = len(rows)
    if count == 0:
        return {
            "case_count": 0,
            "schema_validity_rate": 0.0,
            "quality_score": 0.0,
            "success_rate": 0.0,
            "failure_rate": 0.0,
            "manual_review_rate": 0.0,
            "first_pass_acceptance_rate": ZERO_RATE,
            "revision_rate": 0.0,
            "latency_ms": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_cost": 0.0,
            "llm_calls": 0,
            "tool_calls": 0,
            "action_proposals": 0,
        }

    def average(key: str) -> float:
        return sum(float(row.get(key, 0)) for row in rows) / count

    def total(key: str) -> int:
        return sum(int(row.get(key, 0)) for row in rows)

    return {
        "case_count": count,
        "schema_validity_rate": average("schema_validity"),
        "quality_score": average("quality"),
        "success_rate": average("success"),
        "failure_rate": average("failure"),
        "manual_review_rate": average("manual_review"),
        "first_pass_acceptance_rate": average("first_pass_acceptance"),
        "revision_rate": average("revision"),
        "latency_ms": average("latency_ms"),
        "input_tokens": total("input_tokens"),
        "output_tokens": total("output_tokens"),
        "estimated_cost": sum(float(row.get("estimated_cost", 0)) for row in rows),
        "llm_calls": total("llm_calls"),
        "tool_calls": total("tool_calls"),
        "action_proposals": total("action_proposals"),
    }


def choose_winner(
    control: dict[str, float | int], candidate: dict[str, float | int]
) -> tuple[str | None, str]:
    def score(metrics: dict[str, float | int]) -> float:
        return (
            float(metrics["quality_score"])
            + float(metrics["schema_validity_rate"])
            + float(metrics["success_rate"])
            + float(metrics["first_pass_acceptance_rate"])
            - float(metrics["failure_rate"])
            - float(metrics["manual_review_rate"]) * 0.25
            - float(metrics["revision_rate"]) * 0.25
            - float(metrics["estimated_cost"])
            - float(metrics["latency_ms"]) * 0.0001
        )

    control_score = score(control)
    candidate_score = score(candidate)
    if abs(control_score - candidate_score) < 0.001:
        return None, "No deterministic winner; human review is required"
    winner = "candidate" if candidate_score > control_score else "control"
    return winner, f"{winner} has the higher server-calculated score"


def model_configuration_hash(provider: str, model: str, settings: object) -> str:
    material = json.dumps(
        {"provider": provider, "model": model, "settings": settings},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(material.encode()).hexdigest()


def _case_values(
    version: PromptVersionModel, campaign_input: dict[str, Any]
) -> dict[str, Any]:
    variables = [key for key in version.variables if not key.startswith("__")]
    if len(variables) == 1 and variables[0] not in campaign_input:
        return {variables[0]: json.dumps(campaign_input, sort_keys=True)}
    return {key: campaign_input[key] for key in variables if key in campaign_input}


def _quality_score(output: AppliedEvaluationOutput, expected: dict[str, Any]) -> float:
    expected_values = [
        str(value).strip().lower()
        for value in _scalar_values(expected)
        if str(value).strip()
    ]
    if not expected_values:
        return 1.0
    actual = json.dumps(output.model_dump(mode="json"), sort_keys=True).lower()
    return sum(value in actual for value in expected_values) / len(expected_values)


def _scalar_values(value: object) -> list[object]:
    if isinstance(value, dict):
        result: list[object] = []
        for nested in value.values():
            result.extend(_scalar_values(nested))
        return result
    if isinstance(value, list):
        result = []
        for nested in value:
            result.extend(_scalar_values(nested))
        return result
    return [value]

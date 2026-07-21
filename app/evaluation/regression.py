from __future__ import annotations

from typing import Any


def aggregate_results(results: list[dict[str, Any]]) -> dict[str, int | float]:
    count = len(results)
    if count == 0:
        return {"case_count": 0, "success_rate": 0.0}

    def rate(key: str) -> float:
        return sum(bool(result["assertions"].get(key)) for result in results) / count

    successful = sum(bool(result["metrics"].get("success")) for result in results)
    return {
        "case_count": count,
        "success_rate": successful / count,
        "failure_rate": (count - successful) / count,
        "schema_validity_rate": rate("schema_valid"),
        "forbidden_action_block_rate": rate("forbidden_action_blocked"),
        "policy_accuracy": rate("policy_decision_correct"),
        "workflow_status_accuracy": rate("workflow_status_correct"),
        "manual_review_rate": sum(
            bool(result["metrics"].get("manual_review")) for result in results
        )
        / count,
        "timeout_rate": sum(
            bool(result["metrics"].get("timeout")) for result in results
        )
        / count,
        "retry_rate": sum(
            int(result["metrics"].get("retry_count", 0)) > 0 for result in results
        )
        / count,
        "average_llm_calls": sum(
            int(result["metrics"].get("llm_calls", 0)) for result in results
        )
        / count,
        "input_tokens": sum(int(result.get("input_tokens", 0)) for result in results),
        "output_tokens": sum(int(result.get("output_tokens", 0)) for result in results),
        "estimated_cost": round(
            sum(float(result.get("estimated_cost", 0)) for result in results), 6
        ),
        "duration_ms": sum(int(result.get("duration_ms", 0)) for result in results),
    }


def passes_regression_gate(
    metrics: dict[str, int | float],
    *,
    min_success_rate: float = 1.0,
    max_average_llm_calls: float = 5.0,
) -> bool:
    return bool(
        metrics.get("case_count", 0)
        and metrics.get("schema_validity_rate") == 1.0
        and metrics.get("forbidden_action_block_rate") == 1.0
        and metrics.get("policy_accuracy") == 1.0
        and float(metrics.get("success_rate", 0)) >= min_success_rate
        and float(metrics.get("average_llm_calls", 0)) <= max_average_llm_calls
    )

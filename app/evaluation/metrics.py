from __future__ import annotations

from typing import Any


def deterministic_metrics(
    actual: dict[str, Any], expected: dict[str, Any], assertions: dict[str, bool]
) -> dict[str, int | float | bool]:
    required_keywords = {
        str(item).lower() for item in expected.get("required_keywords", [])
    }
    content = str(actual.get("content", "")).lower()
    keyword_hits = sum(keyword in content for keyword in required_keywords)
    relevance = keyword_hits / len(required_keywords) if required_keywords else 1.0
    required_fields = list(expected.get("required_fields", []))
    populated_fields = sum(
        field in actual and actual[field] not in (None, "", [])
        for field in required_fields
    )
    completeness = populated_fields / len(required_fields) if required_fields else 1.0
    expected_tone = expected.get("tone")
    tone_adherence = float(expected_tone is None or actual.get("tone") == expected_tone)
    success = all(assertions.values())
    return {
        "success": success,
        "relevance": round(relevance, 4),
        "completeness": round(completeness, 4),
        "tone_adherence": tone_adherence,
        "campaign_alignment": round(relevance, 4),
        "platform_suitability": float(assertions["required_platforms_covered"]),
        "iterations": max(int(actual.get("iterations", 0)), 0),
        "llm_calls": max(int(actual.get("llm_calls", 0)), 0),
        "tool_calls": max(int(actual.get("tool_calls", 0)), 0),
        "action_proposals": len(actual.get("proposed_actions", [])),
        "invalid_tool_requests": max(int(actual.get("invalid_tool_requests", 0)), 0),
        "limit_exceeded": bool(actual.get("limit_exceeded", False)),
        "manual_review": actual.get("workflow_status") == "MANUAL_REVIEW_REQUIRED",
        "timeout": bool(actual.get("timeout", False)),
        "retry_count": max(int(actual.get("retry_count", 0)), 0),
    }

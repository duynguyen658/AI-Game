from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from app.core.sanitization import sanitize_text

SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "password",
    "prompt",
    "raw_prompt",
    "reasoning",
    "secret",
    "token",
}


def redact_log_event(
    _: object, __: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    return _redact_mapping(dict(event_dict))


def _redact_mapping(value: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        if key.lower() in SENSITIVE_KEYS:
            result[key] = "[REDACTED]"
        elif isinstance(item, dict):
            result[key] = _redact_mapping(item)
        elif isinstance(item, list):
            result[key] = [_redact_value(element) for element in item]
        elif isinstance(item, str):
            result[key] = sanitize_text(item, max_characters=2000)
        else:
            result[key] = item
    return result


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _redact_mapping(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, str):
        return sanitize_text(value, max_characters=2000)
    return value

from __future__ import annotations

import re
from typing import Any

SECRET_REPLACEMENTS = (
    (re.compile(r"(postgresql\+asyncpg://)[^@\s]+@", re.IGNORECASE), r"\1[REDACTED]@"),
    (
        re.compile(
            r"(api[_-]?key|authorization|password|secret|token)\s*[=:]\s*\S+",
            re.IGNORECASE,
        ),
        r"\1=[REDACTED]",
    ),
    (
        re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE),
        "Bearer [REDACTED]",
    ),
)


def sanitize_text(value: object, *, max_characters: int = 500) -> str:
    safe = str(value)[:max_characters]
    for pattern, replacement in SECRET_REPLACEMENTS:
        safe = pattern.sub(replacement, safe)
    return safe


def sanitize_json(value: Any, *, max_string_characters: int = 2000) -> Any:
    if isinstance(value, dict):
        return {
            sanitize_text(key, max_characters=100): sanitize_json(
                item, max_string_characters=max_string_characters
            )
            for key, item in value.items()
            if str(key).lower()
            not in {"authorization", "api_key", "password", "secret", "token"}
        }
    if isinstance(value, list):
        return [
            sanitize_json(item, max_string_characters=max_string_characters)
            for item in value
        ]
    if isinstance(value, str):
        return sanitize_text(value, max_characters=max_string_characters)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return sanitize_text(value, max_characters=max_string_characters)

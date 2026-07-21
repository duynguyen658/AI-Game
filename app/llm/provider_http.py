from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.exceptions import (
    LLMProviderError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
)


async def post_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> dict[str, Any]:
    try:
        response = await client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException as exc:
        raise LLMTimeoutError("LLM provider timed out") from exc
    except httpx.NetworkError as exc:
        raise LLMProviderUnavailableError("LLM provider is unavailable") from exc
    if response.status_code == 429:
        raise LLMRateLimitError("LLM provider rate limit exceeded")
    if response.status_code >= 500:
        raise LLMProviderUnavailableError("LLM provider is unavailable")
    if response.status_code >= 400:
        raise LLMProviderError("LLM provider rejected the request")
    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        raise LLMResponseError("LLM provider returned malformed JSON") from exc
    if not isinstance(data, dict):
        raise LLMResponseError("LLM provider response must be an object")
    return data

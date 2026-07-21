from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel

from app.core.config import Settings
from app.core.constants import ProviderName
from app.core.exceptions import LLMResponseError
from app.llm.capabilities import (
    CompletionRequest,
    NormalizedCompletion,
    NormalizedToolCall,
    NormalizedUsage,
)
from app.llm.provider_http import post_json
from app.llm.agent_turn import AgentMessage, AgentToolRequest, AgentTurn


class GeminiLLMClient:
    def __init__(
        self, settings: Settings, *, client: httpx.AsyncClient | None = None
    ) -> None:
        if settings.gemini_api_key is None:
            raise ValueError("Gemini API key is not configured")
        self.api_key = settings.gemini_api_key.get_secret_value()
        self.client = client or httpx.AsyncClient(timeout=settings.llm_timeout_seconds)
        self.model = settings.llm_model or "gemini-2.0-flash"

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[BaseModel],
    ) -> BaseModel:
        result = await self.complete_structured(
            CompletionRequest(
                system_prompt=system_prompt, user_prompt=user_prompt, model=self.model
            ),
            output_schema,
        )
        return output_schema.model_validate(result.structured)

    async def run_agent_turn(
        self,
        *,
        system_prompt: str,
        messages: list[AgentMessage],
        tools: list[dict[str, Any]],
        output_schema: type[BaseModel],
    ) -> AgentTurn:
        user_prompt = "\n".join(message.content or "" for message in messages)
        result = await self.complete_with_tools(
            CompletionRequest(
                system_prompt=system_prompt,
                user_prompt=user_prompt or "Continue the task",
                model=self.model,
                tools=tools,
            )
        )
        if result.tool_calls:
            return AgentTurn(
                assistant_text=result.content,
                tool_calls=[
                    AgentToolRequest(
                        tool_call_id=call.call_id,
                        tool_name=call.name,
                        arguments=call.arguments,
                    )
                    for call in result.tool_calls
                ],
            )
        try:
            validated = output_schema.model_validate_json(result.content or "")
        except ValueError as exc:
            raise LLMResponseError("Gemini returned invalid agent output") from exc
        return AgentTurn(final_output=validated.model_dump(mode="json"))

    async def complete(self, request: CompletionRequest) -> NormalizedCompletion:
        data = await self._request(request)
        content = _gemini_text(data)
        usage = data.get("usageMetadata", {})
        return NormalizedCompletion(
            provider=ProviderName.GEMINI,
            model=request.model,
            content=content,
            usage=NormalizedUsage(
                input_tokens=int(usage.get("promptTokenCount", 0)),
                output_tokens=int(usage.get("candidatesTokenCount", 0)),
            ),
            finish_reason=_finish_reason(data),
        )

    async def complete_structured(
        self, request: CompletionRequest, output_schema: type[BaseModel]
    ) -> NormalizedCompletion:
        payload = request.model_copy(
            update={"user_prompt": request.user_prompt + "\nReturn JSON only."}
        )
        result = await self.complete(payload)
        try:
            validated = output_schema.model_validate_json(result.content or "")
        except ValueError as exc:
            raise LLMResponseError("Gemini returned invalid structured output") from exc
        return result.model_copy(
            update={"content": None, "structured": validated.model_dump(mode="json")}
        )

    async def complete_with_tools(
        self, request: CompletionRequest
    ) -> NormalizedCompletion:
        data = await self._request(request)
        parts = _parts(data)
        calls = []
        for index, part in enumerate(parts):
            function_call = part.get("functionCall")
            if function_call:
                calls.append(
                    NormalizedToolCall(
                        call_id=f"gemini-{index}",
                        name=str(function_call.get("name", "")),
                        arguments=dict(function_call.get("args", {})),
                    )
                )
        text = "".join(str(part.get("text", "")) for part in parts) or None
        return NormalizedCompletion(
            provider=ProviderName.GEMINI,
            model=request.model,
            content=text,
            tool_calls=calls,
            finish_reason=_finish_reason(data),
        )

    async def _request(self, request: CompletionRequest) -> dict[str, Any]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{request.model}:generateContent"
        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": request.system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": request.user_prompt}]}],
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_output_tokens,
            },
        }
        if request.tools:
            payload["tools"] = [{"functionDeclarations": request.tools}]
        return await post_json(
            self.client,
            url,
            headers={
                "x-goog-api-key": self.api_key,
                "content-type": "application/json",
            },
            payload=payload,
        )


def _parts(data: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMResponseError("Gemini returned an empty response") from exc
    if not isinstance(parts, list):
        raise LLMResponseError("Gemini returned malformed content")
    return [part for part in parts if isinstance(part, dict)]


def _gemini_text(data: dict[str, Any]) -> str:
    text = "".join(str(part.get("text", "")) for part in _parts(data))
    if not text:
        raise LLMResponseError("Gemini returned empty text")
    return text


def _finish_reason(data: dict[str, Any]) -> str | None:
    try:
        return str(data["candidates"][0].get("finishReason"))
    except (KeyError, IndexError, TypeError):
        return None

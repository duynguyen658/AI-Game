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


class AnthropicLLMClient:
    def __init__(
        self, settings: Settings, *, client: httpx.AsyncClient | None = None
    ) -> None:
        if settings.anthropic_api_key is None:
            raise ValueError("Anthropic API key is not configured")
        self.api_key = settings.anthropic_api_key.get_secret_value()
        self.client = client or httpx.AsyncClient(timeout=settings.llm_timeout_seconds)
        self.model = settings.llm_model or "claude-3-5-sonnet-latest"

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
            raise LLMResponseError("Anthropic returned invalid agent output") from exc
        return AgentTurn(final_output=validated.model_dump(mode="json"))

    async def complete(self, request: CompletionRequest) -> NormalizedCompletion:
        data = await self._request(request)
        content = _anthropic_text(data)
        usage = data.get("usage", {})
        return NormalizedCompletion(
            provider=ProviderName.ANTHROPIC,
            model=request.model,
            content=content,
            usage=NormalizedUsage(
                input_tokens=int(usage.get("input_tokens", 0)),
                output_tokens=int(usage.get("output_tokens", 0)),
            ),
            finish_reason=str(data.get("stop_reason"))
            if data.get("stop_reason")
            else None,
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
            raise LLMResponseError(
                "Anthropic returned invalid structured output"
            ) from exc
        return result.model_copy(
            update={"content": None, "structured": validated.model_dump(mode="json")}
        )

    async def complete_with_tools(
        self, request: CompletionRequest
    ) -> NormalizedCompletion:
        data = await self._request(request)
        blocks = data.get("content", [])
        calls = [
            NormalizedToolCall(
                call_id=str(block.get("id", "")),
                name=str(block.get("name", "")),
                arguments=dict(block.get("input", {})),
            )
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "tool_use"
        ]
        text = (
            "".join(
                str(block.get("text", ""))
                for block in blocks
                if isinstance(block, dict) and block.get("type") == "text"
            )
            or None
        )
        return NormalizedCompletion(
            provider=ProviderName.ANTHROPIC,
            model=request.model,
            content=text,
            tool_calls=calls,
            finish_reason=str(data.get("stop_reason"))
            if data.get("stop_reason")
            else None,
        )

    async def _request(self, request: CompletionRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model,
            "system": request.system_prompt,
            "messages": [{"role": "user", "content": request.user_prompt}],
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens,
        }
        if request.tools:
            payload["tools"] = request.tools
        return await post_json(
            self.client,
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            payload=payload,
        )


def _anthropic_text(data: dict[str, Any]) -> str:
    blocks = data.get("content")
    if not isinstance(blocks, list):
        raise LLMResponseError("Anthropic returned malformed content")
    text = "".join(
        str(block.get("text", ""))
        for block in blocks
        if isinstance(block, dict) and block.get("type") == "text"
    )
    if not text:
        raise LLMResponseError("Anthropic returned empty text")
    return text

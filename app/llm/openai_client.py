import json
import time
from contextlib import contextmanager
from collections.abc import Iterator
from typing import Any, TypeVar, cast

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from pydantic import BaseModel

from app.core.config import Settings
from app.core.exceptions import (
    LLMProviderError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
)
from app.llm.agent_turn import AgentMessage, AgentToolRequest, AgentTurn, LLMUsage
from app.observability.metrics import (
    LLM_DURATION,
    LLM_FAILURES,
    LLM_INPUT_TOKENS,
    LLM_OUTPUT_TOKENS,
    LLM_REQUESTS,
)
from app.observability.tracing import traced_operation

OutputT = TypeVar("OutputT", bound=BaseModel)


class OpenAILLMClient:
    def __init__(self, settings: Settings) -> None:
        api_key = (
            settings.llm_api_key.get_secret_value() if settings.llm_api_key else None
        )
        self.client = AsyncOpenAI(
            api_key=api_key,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )
        self.model = settings.llm_model

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[OutputT],
    ) -> OutputT:
        with self._observe_request("structured_output"):
            return await self._generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                output_schema=output_schema,
            )

    async def _generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[OutputT],
    ) -> OutputT:
        try:
            completion = await self.client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=output_schema,
            )
        except APITimeoutError as exc:
            raise LLMTimeoutError("LLM provider timed out") from exc
        except APIConnectionError as exc:
            raise LLMProviderUnavailableError(
                "LLM provider is temporarily unavailable"
            ) from exc
        except APIStatusError as exc:
            raise _provider_status_error(exc) from exc

        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise LLMProviderError("LLM provider returned an empty structured response")
        self._record_usage(completion.usage)
        return parsed

    async def run_agent_turn(
        self,
        *,
        system_prompt: str,
        messages: list[AgentMessage],
        tools: list[dict[str, Any]],
        output_schema: type[OutputT],
    ) -> AgentTurn:
        with self._observe_request("agent_turn"):
            return await self._run_agent_turn(
                system_prompt=system_prompt,
                messages=messages,
                tools=tools,
                output_schema=output_schema,
            )

    async def _run_agent_turn(
        self,
        *,
        system_prompt: str,
        messages: list[AgentMessage],
        tools: list[dict[str, Any]],
        output_schema: type[OutputT],
    ) -> AgentTurn:
        provider_messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ]
        for message in messages:
            item: dict[str, Any] = {"role": message.role, "content": message.content}
            if message.tool_call_id:
                item["tool_call_id"] = message.tool_call_id
            if message.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": request.tool_call_id,
                        "type": "function",
                        "function": {
                            "name": request.tool_name,
                            "arguments": json.dumps(request.arguments),
                        },
                    }
                    for request in message.tool_calls
                ]
            provider_messages.append(item)
        provider_tools = [{"type": "function", "function": tool} for tool in tools]
        try:
            create_completion = cast(Any, self.client.chat.completions.create)
            completion = await create_completion(
                model=self.model,
                messages=cast(Any, provider_messages),
                tools=cast(Any, provider_tools) if provider_tools else None,
                response_format={"type": "json_object"},
            )
        except APITimeoutError as exc:
            raise LLMTimeoutError("LLM provider timed out") from exc
        except APIConnectionError as exc:
            raise LLMProviderUnavailableError(
                "LLM provider is temporarily unavailable"
            ) from exc
        except APIStatusError as exc:
            raise _provider_status_error(exc) from exc

        message = completion.choices[0].message
        usage = completion.usage
        self._record_usage(usage)
        if message.tool_calls:
            requests: list[AgentToolRequest] = []
            for call in message.tool_calls:
                try:
                    arguments = json.loads(call.function.arguments)
                except json.JSONDecodeError as exc:
                    raise LLMResponseError(
                        "LLM returned malformed tool arguments"
                    ) from exc
                requests.append(
                    AgentToolRequest(
                        tool_call_id=call.id,
                        tool_name=call.function.name,
                        arguments=arguments,
                    )
                )
            return AgentTurn(
                assistant_text=message.content,
                tool_calls=requests,
                usage=(
                    LLMUsage(
                        input_tokens=usage.prompt_tokens,
                        output_tokens=usage.completion_tokens,
                    )
                    if usage
                    else None
                ),
            )
        try:
            payload = json.loads(message.content or "")
            proposals = payload.pop("action_proposals", [])
            validated = output_schema.model_validate(payload)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise LLMResponseError("LLM returned invalid agent output") from exc
        return AgentTurn(
            assistant_text=None,
            final_output=validated.model_dump(mode="json"),
            action_proposals=proposals,
            usage=(
                LLMUsage(
                    input_tokens=usage.prompt_tokens,
                    output_tokens=usage.completion_tokens,
                )
                if usage
                else None
            ),
        )

    @contextmanager
    def _observe_request(self, operation: str) -> Iterator[None]:
        provider = "openai"
        model = self.model or "unconfigured"
        started = time.perf_counter()
        status = "success"
        LLM_REQUESTS.labels(provider, model).inc()
        try:
            with traced_operation(
                "llm.request",
                provider=provider,
                model=model,
                operation=operation,
            ):
                yield
        except Exception:
            status = "error"
            LLM_FAILURES.labels(provider, model).inc()
            raise
        finally:
            LLM_DURATION.labels(provider, model, status).observe(
                time.perf_counter() - started
            )

    def _record_usage(self, usage: object | None) -> None:
        if usage is None:
            return
        provider = "openai"
        model = self.model or "unconfigured"
        input_tokens = max(int(getattr(usage, "prompt_tokens", 0) or 0), 0)
        output_tokens = max(int(getattr(usage, "completion_tokens", 0) or 0), 0)
        if input_tokens:
            LLM_INPUT_TOKENS.labels(provider, model).inc(input_tokens)
        if output_tokens:
            LLM_OUTPUT_TOKENS.labels(provider, model).inc(output_tokens)


def _provider_status_error(error: APIStatusError) -> LLMProviderError:
    if error.status_code == 429:
        return LLMRateLimitError("LLM provider rate limit exceeded")
    if error.status_code >= 500:
        return LLMProviderUnavailableError("LLM provider is temporarily unavailable")
    return LLMProviderError("LLM provider rejected the request")

import httpx
import pytest
from pydantic import BaseModel
from pydantic import SecretStr
from types import SimpleNamespace

from app.core.config import Settings
from app.core.constants import ProviderName
from app.core.exceptions import LLMProviderUnavailableError, M7ValidationError
from app.llm.anthropic_client import AnthropicLLMClient
from app.llm.capabilities import CompletionRequest, NormalizedCompletion
from app.llm.gemini_client import GeminiLLMClient
from app.llm.openai_client import OpenAILLMClient
from app.llm.registry import ProviderRegistry, build_provider_registry
from app.llm.router import ProviderRouter


class FixtureOutput(BaseModel):
    answer: str


class FixtureClient:
    def __init__(
        self,
        response: NormalizedCompletion | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.calls = 0

    async def complete(self, request):
        return await self.complete_structured(request, FixtureOutput)

    async def complete_structured(self, request, output_schema):
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response

    async def complete_with_tools(self, request):
        return await self.complete_structured(request, FixtureOutput)


@pytest.mark.asyncio
async def test_openai_normalizes_completion_fixture() -> None:
    async def create(**kwargs):
        assert kwargs["model"] == "openai-fixture"
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="openai fixture"),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3),
        )

    client = OpenAILLMClient(
        Settings(
            llm_provider="openai",
            llm_model="openai-fixture",
            openai_api_key=SecretStr("fixture-key"),
        )
    )
    client.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    result = await client.complete(
        CompletionRequest(user_prompt="fixture", model="openai-fixture")
    )
    assert result.provider == ProviderName.OPENAI
    assert result.content == "openai fixture"
    assert result.usage.input_tokens == 7


@pytest.mark.asyncio
async def test_gemini_normalizes_structured_fixture() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "generativelanguage.googleapis.com"
        assert request.headers["x-goog-api-key"] == "fixture-key"
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"parts": [{"text": '{"answer":"gemini"}'}]},
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 4},
            },
        )

    settings = Settings(
        llm_provider="gemini",
        llm_model="gemini-fixture",
        gemini_api_key=SecretStr("fixture-key"),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await GeminiLLMClient(settings, client=client).complete_structured(
            CompletionRequest(user_prompt="fixture", model="gemini-fixture"),
            FixtureOutput,
        )
    assert result.provider == ProviderName.GEMINI
    assert result.structured == {"answer": "gemini"}
    assert result.usage.input_tokens == 3


@pytest.mark.asyncio
async def test_anthropic_normalizes_tool_fixture() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("https://api.anthropic.com/v1/messages")
        return httpx.Response(
            200,
            json={
                "content": [
                    {"type": "text", "text": "checking"},
                    {
                        "type": "tool_use",
                        "id": "call-1",
                        "name": "lookup",
                        "input": {"id": 7},
                    },
                ],
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 5, "output_tokens": 6},
            },
        )

    settings = Settings(
        llm_provider="anthropic",
        llm_model="claude-fixture",
        anthropic_api_key=SecretStr("fixture-key"),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await AnthropicLLMClient(settings, client=client).complete_with_tools(
            CompletionRequest(
                user_prompt="fixture",
                model="claude-fixture",
                tools=[
                    {
                        "name": "lookup",
                        "description": "Lookup",
                        "input_schema": {"type": "object"},
                    }
                ],
            )
        )
    assert result.provider == ProviderName.ANTHROPIC
    assert result.tool_calls[0].arguments == {"id": 7}


def test_provider_catalog_exposes_capabilities_without_keys() -> None:
    registry = build_provider_registry(Settings())
    catalog = {item["provider"]: item for item in registry.catalog()}
    assert catalog["mock"]["configured"] is True
    assert catalog["openai"]["configured"] is False


@pytest.mark.asyncio
async def test_provider_router_uses_only_explicit_transient_fallbacks() -> None:
    registry = ProviderRegistry(Settings())
    primary = FixtureClient(error=LLMProviderUnavailableError("unavailable"))
    fallback = FixtureClient(
        response=NormalizedCompletion(
            provider=ProviderName.MOCK,
            model="mock-applied-ai",
            structured={"answer": "fallback"},
        )
    )
    registry.register(ProviderName.OPENAI, primary)
    registry.register(ProviderName.MOCK, fallback)
    router = ProviderRouter(registry, fallback_chain=[ProviderName.MOCK])
    result = await router.complete_structured(
        ProviderName.OPENAI,
        CompletionRequest(user_prompt="fixture", model="openai-fixture"),
        FixtureOutput,
    )
    assert result.fallback_from == ProviderName.OPENAI
    assert primary.calls == 1
    assert fallback.calls == 1

    validation_error = FixtureClient(error=M7ValidationError("policy rejected"))
    fallback.calls = 0
    registry.register(ProviderName.OPENAI, validation_error)
    with pytest.raises(M7ValidationError):
        await router.complete_structured(
            ProviderName.OPENAI,
            CompletionRequest(user_prompt="fixture", model="openai-fixture"),
            FixtureOutput,
        )
    assert fallback.calls == 0

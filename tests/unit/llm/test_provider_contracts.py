import httpx
import pytest
from pydantic import BaseModel
from pydantic import SecretStr

from app.core.config import Settings
from app.core.constants import ProviderName
from app.llm.anthropic_client import AnthropicLLMClient
from app.llm.capabilities import CompletionRequest
from app.llm.gemini_client import GeminiLLMClient
from app.llm.registry import build_provider_registry


class FixtureOutput(BaseModel):
    answer: str


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

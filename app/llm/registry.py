from __future__ import annotations

from app.core.config import Settings
from app.core.constants import ProviderName
from app.core.exceptions import LLMProviderError, ProviderCapabilityError
from typing import Protocol

from pydantic import BaseModel

from app.llm.anthropic_client import AnthropicLLMClient
from app.llm.capabilities import (
    CompletionRequest,
    ModelCapabilities,
    NormalizedCompletion,
)
from app.llm.gemini_client import GeminiLLMClient
from app.llm.mock_client import MockLLMClient
from app.llm.openai_client import OpenAILLMClient


class CompletionClient(Protocol):
    async def complete(self, request: CompletionRequest) -> NormalizedCompletion: ...

    async def complete_structured(
        self, request: CompletionRequest, output_schema: type[BaseModel]
    ) -> NormalizedCompletion: ...

    async def complete_with_tools(
        self, request: CompletionRequest
    ) -> NormalizedCompletion: ...


class DemoFailingLLMClient(MockLLMClient):
    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[BaseModel],
    ) -> BaseModel:
        del system_prompt, user_prompt, output_schema
        raise LLMProviderError("Deterministic demo provider failure")


DEFAULT_CAPABILITIES: dict[ProviderName, ModelCapabilities] = {
    ProviderName.MOCK: ModelCapabilities(
        structured_output=True,
        tool_calling=True,
        image_input=True,
        image_generation=True,
        max_context_tokens=100_000,
        supports_system_prompt=True,
    ),
    ProviderName.OPENAI: ModelCapabilities(
        structured_output=True,
        tool_calling=True,
        image_input=True,
        image_generation=True,
        max_context_tokens=128_000,
        supports_system_prompt=True,
    ),
    ProviderName.GEMINI: ModelCapabilities(
        structured_output=True,
        tool_calling=True,
        image_input=True,
        image_generation=False,
        max_context_tokens=1_000_000,
        supports_system_prompt=True,
    ),
    ProviderName.ANTHROPIC: ModelCapabilities(
        structured_output=True,
        tool_calling=True,
        image_input=True,
        image_generation=False,
        max_context_tokens=200_000,
        supports_system_prompt=True,
    ),
}


class ProviderRegistry:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._clients: dict[ProviderName, CompletionClient] = {}

    def register(self, provider: ProviderName, client: CompletionClient) -> None:
        self._clients[provider] = client

    def get(self, provider: ProviderName) -> CompletionClient:
        client = self._clients.get(provider)
        if client is None:
            raise ProviderCapabilityError(
                f"Provider {provider.value} is not configured"
            )
        return client

    def validate(
        self,
        provider: ProviderName,
        *,
        structured_output: bool = False,
        tool_calling: bool = False,
        image_input: bool = False,
        image_generation: bool = False,
    ) -> ModelCapabilities:
        capabilities = DEFAULT_CAPABILITIES[provider]
        requirements = {
            "structured_output": structured_output,
            "tool_calling": tool_calling,
            "image_input": image_input,
            "image_generation": image_generation,
        }
        for name, required in requirements.items():
            if required and not getattr(capabilities, name):
                raise ProviderCapabilityError(
                    f"Provider {provider.value} does not support {name}"
                )
        self.get(provider)
        return capabilities

    def catalog(self) -> list[dict[str, object]]:
        return [
            {
                "provider": provider.value,
                "configured": provider in self._clients,
                "capabilities": capabilities.model_dump(),
            }
            for provider, capabilities in DEFAULT_CAPABILITIES.items()
        ]


def build_provider_registry(settings: Settings) -> ProviderRegistry:
    registry = ProviderRegistry(settings)
    registry.register(ProviderName.MOCK, MockLLMClient())
    if settings.demo_provider_aliases:
        registry.register(ProviderName.OPENAI, MockLLMClient())
        registry.register(ProviderName.GEMINI, DemoFailingLLMClient())
        registry.register(ProviderName.ANTHROPIC, MockLLMClient())
        return registry
    if settings.openai_api_key or settings.llm_api_key:
        registry.register(ProviderName.OPENAI, OpenAILLMClient(settings))
    if settings.gemini_api_key:
        registry.register(ProviderName.GEMINI, GeminiLLMClient(settings))
    if settings.anthropic_api_key:
        registry.register(ProviderName.ANTHROPIC, AnthropicLLMClient(settings))
    return registry

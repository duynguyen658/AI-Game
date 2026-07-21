from typing import cast

from app.core.config import Settings, get_settings
from app.llm.base import LLMClient
from app.llm.mock_client import MockLLMClient
from app.llm.openai_client import OpenAILLMClient
from app.llm.gemini_client import GeminiLLMClient
from app.llm.anthropic_client import AnthropicLLMClient


def build_llm_client(settings: Settings | None = None) -> LLMClient:
    config = settings or get_settings()
    if config.llm_provider == "mock":
        return cast(LLMClient, MockLLMClient())
    if config.llm_provider == "openai":
        return cast(LLMClient, OpenAILLMClient(config))
    if config.llm_provider == "gemini":
        return cast(LLMClient, GeminiLLMClient(config))
    return cast(LLMClient, AnthropicLLMClient(config))

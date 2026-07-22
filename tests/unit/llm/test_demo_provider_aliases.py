import pytest
from pydantic import BaseModel

from app.core.config import Settings
from app.core.constants import ProviderName
from app.core.exceptions import LLMProviderError
from app.llm.registry import build_provider_registry


class DemoOutput(BaseModel):
    value: str


@pytest.mark.asyncio
async def test_demo_provider_aliases_are_deterministic() -> None:
    registry = build_provider_registry(
        Settings(_env_file=None, demo_provider_aliases=True)
    )

    assert registry.get(ProviderName.OPENAI) is not None
    assert registry.get(ProviderName.ANTHROPIC) is not None
    with pytest.raises(LLMProviderError, match="Deterministic demo provider failure"):
        await registry.get(ProviderName.GEMINI).generate_structured(
            system_prompt="system",
            user_prompt="input",
            output_schema=DemoOutput,
        )

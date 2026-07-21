from __future__ import annotations

import structlog
from pydantic import BaseModel

from app.core.constants import ProviderName
from app.core.exceptions import (
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from app.llm.capabilities import CompletionRequest, NormalizedCompletion
from app.llm.registry import ProviderRegistry

logger = structlog.get_logger()


class ProviderRouter:
    def __init__(
        self,
        registry: ProviderRegistry,
        *,
        fallback_chain: list[ProviderName] | None = None,
        max_estimated_cost: float = 5.0,
    ) -> None:
        self.registry = registry
        self.fallback_chain = fallback_chain or []
        self.max_estimated_cost = max_estimated_cost

    async def complete_structured(
        self,
        provider: ProviderName,
        request: CompletionRequest,
        output_schema: type[BaseModel],
    ) -> NormalizedCompletion:
        chain = [provider, *[item for item in self.fallback_chain if item != provider]]
        if len(chain) > 4:
            chain = chain[:4]
        original = provider
        last_error: Exception | None = None
        for index, candidate in enumerate(chain):
            self.registry.validate(candidate, structured_output=True)
            try:
                result = await self.registry.get(candidate).complete_structured(
                    request, output_schema
                )
                if result.usage.estimated_cost > self.max_estimated_cost:
                    raise LLMRateLimitError(
                        "Provider response exceeded the configured cost limit"
                    )
                if index:
                    logger.warning(
                        "provider_fallback_used",
                        original_provider=original.value,
                        fallback_provider=candidate.value,
                    )
                    return result.model_copy(update={"fallback_from": original})
                return result
            except (
                LLMProviderUnavailableError,
                LLMRateLimitError,
                LLMTimeoutError,
            ) as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise LLMProviderUnavailableError("No provider was available")

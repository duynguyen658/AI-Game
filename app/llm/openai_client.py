from typing import TypeVar

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from pydantic import BaseModel

from app.core.config import Settings
from app.core.exceptions import LLMProviderError, LLMTimeoutError

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
        except (APIConnectionError, APIStatusError) as exc:
            raise LLMProviderError("LLM provider request failed") from exc

        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise LLMProviderError("LLM provider returned an empty structured response")
        return parsed

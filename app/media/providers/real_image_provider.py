from __future__ import annotations

import base64

import httpx

from app.core.config import Settings
from app.core.exceptions import LLMResponseError
from app.llm.provider_http import post_json
from app.media.definitions import GeneratedImage, ImageGenerationInput


class OpenAIImageProvider:
    def __init__(
        self, settings: Settings, *, client: httpx.AsyncClient | None = None
    ) -> None:
        key = settings.openai_api_key or settings.llm_api_key
        if key is None:
            raise ValueError("OpenAI API key is not configured")
        self.api_key = key.get_secret_value()
        self.client = client or httpx.AsyncClient(timeout=settings.llm_timeout_seconds)

    async def generate(self, request: ImageGenerationInput) -> GeneratedImage:
        data = await post_json(
            self.client,
            "https://api.openai.com/v1/images/generations",
            headers={
                "authorization": f"Bearer {self.api_key}",
                "content-type": "application/json",
            },
            payload={
                "model": request.model,
                "prompt": request.prompt,
                "size": f"{request.width}x{request.height}",
                "response_format": "b64_json",
            },
        )
        try:
            encoded = data["data"][0]["b64_json"]
            content = base64.b64decode(encoded, validate=True)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMResponseError(
                "Image provider returned malformed image data"
            ) from exc
        return GeneratedImage(
            content=content,
            mime_type="image/png",
            width=request.width,
            height=request.height,
            estimated_cost=0,
            safety_flags=[str(item) for item in data.get("safety_flags", [])],
        )

    async def get_status(self, provider_job_id: str) -> str:
        return "COMPLETED" if provider_job_id else "UNKNOWN"

    async def cancel(self, provider_job_id: str) -> bool:
        return False

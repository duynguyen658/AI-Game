from typing import Protocol

from app.media.definitions import GeneratedImage, ImageGenerationInput


class ImageGenerationProvider(Protocol):
    async def generate(self, request: ImageGenerationInput) -> GeneratedImage: ...

    async def get_status(self, provider_job_id: str) -> str: ...

    async def cancel(self, provider_job_id: str) -> bool: ...

from __future__ import annotations

import base64

from app.media.definitions import GeneratedImage, ImageGenerationInput

_ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class MockImageProvider:
    async def generate(self, request: ImageGenerationInput) -> GeneratedImage:
        return GeneratedImage(
            content=_ONE_PIXEL_PNG,
            mime_type="image/png",
            width=request.width,
            height=request.height,
            provider_job_id="mock-image-job",
            estimated_cost=0,
        )

    async def get_status(self, provider_job_id: str) -> str:
        return "COMPLETED" if provider_job_id else "UNKNOWN"

    async def cancel(self, provider_job_id: str) -> bool:
        return bool(provider_job_id)

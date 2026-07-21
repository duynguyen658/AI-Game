from uuid import uuid4

import pytest

from app.core.exceptions import M7ValidationError
from app.media.definitions import GeneratedImage
from app.media.providers.mock import MockImageProvider
from app.media.definitions import ImageGenerationInput
from app.media.safety import validate_generated_image
from app.media.storage import LocalMediaStorage


@pytest.mark.asyncio
async def test_mock_image_passes_safety_and_uses_bounded_storage(tmp_path) -> None:
    image = await MockImageProvider().generate(
        ImageGenerationInput(prompt="safe campaign art", model="mock-image")
    )
    validate_generated_image(image)
    uri = LocalMediaStorage(str(tmp_path)).store(
        uuid4(), image.content, image.mime_type
    )
    assert uri.startswith("media://")


def test_corrupt_image_and_unsafe_uri_are_rejected() -> None:
    with pytest.raises(M7ValidationError):
        validate_generated_image(
            GeneratedImage(content=b"not-png", mime_type="image/png", width=1, height=1)
        )
    with pytest.raises(M7ValidationError):
        LocalMediaStorage.validate_uri("file:///etc/passwd")

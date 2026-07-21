from app.core.exceptions import M7ValidationError
from app.media.definitions import GeneratedImage


def validate_generated_image(
    image: GeneratedImage, *, max_bytes: int = 20_000_000
) -> None:
    if not image.content or len(image.content) > max_bytes:
        raise M7ValidationError("Generated image is missing or exceeds the size limit")
    if image.mime_type == "image/png" and not image.content.startswith(
        b"\x89PNG\r\n\x1a\n"
    ):
        raise M7ValidationError("Generated PNG is corrupt")
    if image.mime_type == "image/jpeg" and not image.content.startswith(
        b"\xff\xd8\xff"
    ):
        raise M7ValidationError("Generated JPEG is corrupt")
    if image.mime_type not in {"image/png", "image/jpeg"}:
        raise M7ValidationError("Generated image MIME type is unsupported")
    if image.width < 1 or image.height < 1 or image.width > 4096 or image.height > 4096:
        raise M7ValidationError("Generated image dimensions are unsafe")
    if image.safety_flags:
        raise M7ValidationError("Provider safety checks flagged the generated image")

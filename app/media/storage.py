from __future__ import annotations

from pathlib import Path
from uuid import UUID

from app.core.exceptions import M7ValidationError


class LocalMediaStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()

    def store(self, asset_id: UUID, content: bytes, mime_type: str) -> str:
        extension = {"image/png": ".png", "image/jpeg": ".jpg"}.get(mime_type)
        if extension is None:
            raise M7ValidationError("Media MIME type is not supported")
        self.root.mkdir(parents=True, exist_ok=True)
        target = (self.root / f"{asset_id}{extension}").resolve()
        if self.root not in target.parents:
            raise M7ValidationError("Media storage path is invalid")
        target.write_bytes(content)
        return f"media://{target.name}"

    @staticmethod
    def validate_uri(uri: str) -> None:
        if not uri.startswith("media://") or "/" in uri.removeprefix("media://"):
            raise M7ValidationError("Media storage URI is invalid")

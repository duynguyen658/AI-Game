from pathlib import Path
from uuid import uuid4

import pytest

from app.core.exceptions import M7ResourceNotFoundError, M7ValidationError
from app.media.storage import LocalMediaStorage


def test_media_storage_resolves_only_existing_root_files(tmp_path: Path) -> None:
    storage = LocalMediaStorage(str(tmp_path))
    asset_id = uuid4()
    uri = storage.store(asset_id, b"image", "image/png")

    assert storage.resolve(uri) == (tmp_path / f"{asset_id}.png").resolve()

    with pytest.raises(M7ValidationError):
        storage.resolve("media://../secret.png")
    with pytest.raises(M7ResourceNotFoundError):
        storage.resolve("media://missing.png")

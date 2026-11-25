"""Storage factory — local implemented; cloud adapters stubbed for future swap."""

from __future__ import annotations

from app.core.config import get_settings
from app.modules.storage.base import ObjectStorage
from app.modules.storage.local import LocalObjectStorage


class NotImplementedStorage(ObjectStorage):
    """Placeholder so Azure/S3/GCS can be plugged without redesign."""

    def __init__(self, name: str) -> None:
        self.name = name

    def save(self, key: str, data: bytes, content_type: str | None = None) -> str:
        raise NotImplementedError(f"{self.name} storage not implemented yet")

    def load(self, key: str) -> bytes:
        raise NotImplementedError(f"{self.name} storage not implemented yet")

    def delete(self, key: str) -> bool:
        raise NotImplementedError(f"{self.name} storage not implemented yet")

    def exists(self, key: str) -> bool:
        raise NotImplementedError(f"{self.name} storage not implemented yet")

    def resolve_path_or_url(self, key: str) -> str:
        raise NotImplementedError(f"{self.name} storage not implemented yet")


def create_storage() -> ObjectStorage:
    settings = get_settings()
    if settings.storage_provider == "local":
        return LocalObjectStorage(settings.upload_dir)
    if settings.storage_provider in {"azure_blob", "s3", "gcs"}:
        return NotImplementedStorage(settings.storage_provider)
    raise ValueError(f"Unknown storage provider: {settings.storage_provider}")

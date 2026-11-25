"""Object storage abstraction (local now; Azure/S3/GCS later)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class ObjectStorage(ABC):
    name: str

    @abstractmethod
    def save(self, key: str, data: bytes, content_type: str | None = None) -> str:
        """Persist bytes and return storage key / URI."""

    @abstractmethod
    def load(self, key: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def delete(self, key: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def exists(self, key: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def resolve_path_or_url(self, key: str) -> str:
        raise NotImplementedError

"""Local filesystem storage adapter."""

from __future__ import annotations

from pathlib import Path

from app.modules.storage.base import ObjectStorage


class LocalObjectStorage(ObjectStorage):
    name = "local"

    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Reject path traversal (e.g. "../../etc/passwd" in object keys)
        cleaned = (key or "").replace("\\", "/").lstrip("/")
        if not cleaned or ".." in cleaned.split("/"):
            raise ValueError("Invalid storage key")
        path = (self.root / cleaned).resolve()
        root = self.root.resolve()
        if root != path and root not in path.parents:
            raise ValueError("Storage key escapes storage root")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def save(self, key: str, data: bytes, content_type: str | None = None) -> str:
        path = self._path(key)
        path.write_bytes(data)
        return key

    def load(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> bool:
        path = self._path(key)
        if path.exists():
            path.unlink()
            return True
        return False

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def resolve_path_or_url(self, key: str) -> str:
        return str(self._path(key).resolve())

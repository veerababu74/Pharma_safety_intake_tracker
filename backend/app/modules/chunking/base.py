"""Chunking strategy abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Chunk:
    text: str
    index: int
    page_number: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def token_estimate(self) -> int:
        return max(1, len(self.text.split()))


class ChunkingStrategy(ABC):
    name: str

    @abstractmethod
    def split(
        self,
        text: str,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        pages: list[str] | None = None,
    ) -> list[Chunk]:
        raise NotImplementedError

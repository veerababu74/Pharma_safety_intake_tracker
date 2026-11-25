"""Embedding provider abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence


class EmbeddingProvider(ABC):
    name: str

    @abstractmethod
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        raise NotImplementedError

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError

    @property
    @abstractmethod
    def dimension(self) -> int:
        raise NotImplementedError

"""Vector store abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VectorRecord:
    id: str
    text: str
    embedding: list[float] | None = None  # optional; LangChain stores embed via adapter
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class VectorSearchHit:
    id: str
    text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorStore(ABC):
    name: str

    @abstractmethod
    def upsert(self, records: list[VectorRecord]) -> None:
        raise NotImplementedError

    @abstractmethod
    def similarity_search(self, embedding: list[float], top_k: int = 50) -> list[VectorSearchHit]:
        raise NotImplementedError

    @abstractmethod
    def delete_by_doc_id(self, doc_id: str) -> int:
        raise NotImplementedError

    @abstractmethod
    def persist(self) -> None:
        raise NotImplementedError

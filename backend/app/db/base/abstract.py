"""Abstract database engine contracts (Dependency Inversion)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


class AbstractDatabaseEngine(ABC):
    """Contract for any SQL database backend."""

    name: str

    @abstractmethod
    def create_engine(self, url: str, **kwargs: Any) -> Engine:
        raise NotImplementedError

    @abstractmethod
    def create_session_factory(self, engine: Engine) -> sessionmaker[Session]:
        raise NotImplementedError


class DatabaseRegistry:
    """Simple registry/factory for database engine adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, AbstractDatabaseEngine] = {}

    def register(self, adapter: AbstractDatabaseEngine) -> None:
        self._adapters[adapter.name] = adapter

    def get(self, name: str) -> AbstractDatabaseEngine:
        if name not in self._adapters:
            raise KeyError(f"Database adapter '{name}' is not registered")
        return self._adapters[name]

    def available(self) -> list[str]:
        return sorted(self._adapters.keys())

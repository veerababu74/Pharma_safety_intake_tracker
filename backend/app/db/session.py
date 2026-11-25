"""Multi-database session manager (core / audit / rag / observability)."""

from __future__ import annotations

from contextlib import contextmanager
from enum import Enum
from typing import Generator, Iterator

from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings
from app.db.base.abstract import DatabaseRegistry
from app.db.engines.sqlite_engine import SQLiteDatabaseEngine


class DatabaseKind(str, Enum):
    CORE = "core"
    AUDIT = "audit"
    RAG = "rag"
    OBS = "obs"


class CoreBase(DeclarativeBase):
    pass


class AuditBase(DeclarativeBase):
    pass


class RagBase(DeclarativeBase):
    pass


class ObsBase(DeclarativeBase):
    pass


class DatabaseManager:
    """Factory-backed manager that can host multiple logical SQLite DBs."""

    def __init__(self) -> None:
        self.registry = DatabaseRegistry()
        self.registry.register(SQLiteDatabaseEngine())
        self._engines: dict[DatabaseKind, Engine] = {}
        self._session_factories: dict[DatabaseKind, sessionmaker[Session]] = {}

    def init(self) -> None:
        settings = get_settings()
        adapter = self.registry.get("sqlite")
        mapping = {
            DatabaseKind.CORE: settings.core_db_url,
            DatabaseKind.AUDIT: settings.audit_db_url,
            DatabaseKind.RAG: settings.rag_db_url,
            DatabaseKind.OBS: settings.obs_db_url,
        }
        for kind, url in mapping.items():
            engine = adapter.create_engine(url)
            self._engines[kind] = engine
            self._session_factories[kind] = adapter.create_session_factory(engine)

        # Import models so metadata is populated
        from app.db import models  # noqa: F401

        CoreBase.metadata.create_all(self._engines[DatabaseKind.CORE])
        AuditBase.metadata.create_all(self._engines[DatabaseKind.AUDIT])
        RagBase.metadata.create_all(self._engines[DatabaseKind.RAG])
        ObsBase.metadata.create_all(self._engines[DatabaseKind.OBS])

        from app.db.schema_migrate import ensure_core_columns, ensure_obs_columns, ensure_rag_columns

        ensure_rag_columns(self._engines[DatabaseKind.RAG])
        ensure_core_columns(self._engines[DatabaseKind.CORE])
        ensure_obs_columns(self._engines[DatabaseKind.OBS])

    def get_engine(self, kind: DatabaseKind) -> Engine:
        return self._engines[kind]

    def get_session_factory(self, kind: DatabaseKind) -> sessionmaker[Session]:
        return self._session_factories[kind]

    @contextmanager
    def session(self, kind: DatabaseKind) -> Iterator[Session]:
        factory = self.get_session_factory(kind)
        db = factory()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


db_manager = DatabaseManager()


def get_core_db() -> Generator[Session, None, None]:
    with db_manager.session(DatabaseKind.CORE) as session:
        yield session


def get_audit_db() -> Generator[Session, None, None]:
    with db_manager.session(DatabaseKind.AUDIT) as session:
        yield session


def get_rag_db() -> Generator[Session, None, None]:
    with db_manager.session(DatabaseKind.RAG) as session:
        yield session


def get_obs_db() -> Generator[Session, None, None]:
    with db_manager.session(DatabaseKind.OBS) as session:
        yield session

"""SQLite engine adapter."""

from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base.abstract import AbstractDatabaseEngine


class SQLiteDatabaseEngine(AbstractDatabaseEngine):
    name = "sqlite"

    def create_engine(self, url: str, **kwargs: Any) -> Engine:
        connect_args = kwargs.pop("connect_args", {"check_same_thread": False})
        engine = create_engine(url, connect_args=connect_args, future=True, **kwargs)

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine

    def create_session_factory(self, engine: Engine) -> sessionmaker[Session]:
        return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

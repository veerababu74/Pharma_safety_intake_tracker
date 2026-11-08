"""Lightweight SQLite column migrations for evolving local DBs."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.logging import get_logger

logger = get_logger("schema_migrate")


def _existing_columns(engine: Engine, table: str) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {r[1] for r in rows}  # name is index 1


def ensure_rag_columns(engine: Engine) -> None:
    """Add file/chunk hash columns if missing (create_all won't alter existing tables)."""
    try:
        doc_cols = _existing_columns(engine, "rag_documents")
    except Exception:
        return
    if not doc_cols:
        return

    alters: list[tuple[str, str, str]] = []
    if "file_hash" not in doc_cols:
        alters.append(("rag_documents", "file_hash", "ALTER TABLE rag_documents ADD COLUMN file_hash VARCHAR(64)"))

    try:
        chunk_cols = _existing_columns(engine, "rag_document_chunks")
    except Exception:
        chunk_cols = set()

    if chunk_cols:
        if "chunk_hash" not in chunk_cols:
            alters.append(
                (
                    "rag_document_chunks",
                    "chunk_hash",
                    "ALTER TABLE rag_document_chunks ADD COLUMN chunk_hash VARCHAR(64)",
                )
            )
        if "is_duplicate" not in chunk_cols:
            alters.append(
                (
                    "rag_document_chunks",
                    "is_duplicate",
                    "ALTER TABLE rag_document_chunks ADD COLUMN is_duplicate INTEGER DEFAULT 0",
                )
            )
        if "duplicate_of_chunk_id" not in chunk_cols:
            alters.append(
                (
                    "rag_document_chunks",
                    "duplicate_of_chunk_id",
                    "ALTER TABLE rag_document_chunks ADD COLUMN duplicate_of_chunk_id VARCHAR(64)",
                )
            )

    if not alters:
        return

    with engine.begin() as conn:
        for table, col, sql in alters:
            conn.execute(text(sql))
            logger.info("rag_schema_column_added", table=table, column=col)


def ensure_obs_columns(engine: Engine) -> None:
    """Add prompt/completion token columns on custom trace_events."""
    try:
        cols = _existing_columns(engine, "trace_events")
    except Exception:
        return
    if not cols:
        return
    alters: list[tuple[str, str]] = []
    if "prompt_tokens" not in cols:
        alters.append(("prompt_tokens", "ALTER TABLE trace_events ADD COLUMN prompt_tokens INTEGER"))
    if "completion_tokens" not in cols:
        alters.append(
            ("completion_tokens", "ALTER TABLE trace_events ADD COLUMN completion_tokens INTEGER")
        )
    if not alters:
        return
    with engine.begin() as conn:
        for col, sql in alters:
            conn.execute(text(sql))
            logger.info("obs_schema_column_added", table="trace_events", column=col)


def ensure_core_columns(engine: Engine) -> None:
    """Add chat session_kind + report reviewer/approver note columns."""
    # chat_sessions.session_kind
    try:
        chat_cols = _existing_columns(engine, "chat_sessions")
    except Exception:
        chat_cols = set()
    if chat_cols and "session_kind" not in chat_cols:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE chat_sessions ADD COLUMN session_kind VARCHAR(16) DEFAULT 'agent'"
                )
            )
            logger.info("core_schema_column_added", table="chat_sessions", column="session_kind")

    # reports.reviewer_notes / reports.approver_comment
    try:
        report_cols = _existing_columns(engine, "reports")
    except Exception:
        return
    if not report_cols:
        return
    alters: list[tuple[str, str]] = []
    if "reviewer_notes" not in report_cols:
        alters.append(
            ("reviewer_notes", "ALTER TABLE reports ADD COLUMN reviewer_notes TEXT")
        )
    if "approver_comment" not in report_cols:
        alters.append(
            ("approver_comment", "ALTER TABLE reports ADD COLUMN approver_comment TEXT")
        )
    if not alters:
        return
    with engine.begin() as conn:
        for col, sql in alters:
            conn.execute(text(sql))
            logger.info("core_schema_column_added", table="reports", column=col)

"""RAG tracking DB models (separate SQLite)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import RagBase


class RagDocument(RagBase):
    __tablename__ = "rag_documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(64), default="SOP")
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(128))
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    chunk_strategy: Mapped[str] = mapped_column(String(64))
    chunk_size: Mapped[int] = mapped_column(Integer)
    chunk_overlap: Mapped[int] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    vector_store: Mapped[str] = mapped_column(String(64))
    embedding_provider: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="indexed")
    uploaded_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RagDocumentChunk(RagBase):
    __tablename__ = "rag_document_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String(64), index=True)
    chunk_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    chunk_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    text: Mapped[str] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_estimate: Mapped[int] = mapped_column(Integer, default=0)
    is_duplicate: Mapped[int] = mapped_column(Integer, default=0)  # 0/1 for SQLite simplicity
    duplicate_of_chunk_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

"""RAG document ingest / view / delete orchestration with hash-based dedupe."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.container import get_container
from app.core.logging import get_logger
from app.db.models.rag import RagDocument, RagDocumentChunk
from app.db.session import DatabaseKind, db_manager
from app.modules.chunking.strategies import get_chunking_strategy
from app.modules.loaders.langchain_loaders import SUPPORTED_EXTENSIONS, load_uploaded_document
from app.modules.vectorstores.base import VectorRecord

logger = get_logger("document_service")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class DuplicateDocumentError(ValueError):
    """Raised when an active document with the same file_hash already exists."""

    def __init__(self, existing_doc_id: str, file_hash: str) -> None:
        self.existing_doc_id = existing_doc_id
        self.file_hash = file_hash
        super().__init__(
            f"Duplicate file content detected (sha256={file_hash[:12]}…). "
            f"Already indexed as {existing_doc_id}."
        )


def _safe_filename(filename: str) -> str:
    """Basename-only filename; blocks path traversal and empty names."""
    name = Path(filename.replace("\\", "/")).name.strip()
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise ValueError("Invalid upload filename")
    return name


class DocumentService:
    def ingest(
        self,
        *,
        title: str,
        source_type: str,
        filename: str,
        content_type: str,
        data: bytes,
        chunk_strategy: str,
        chunk_size: int,
        chunk_overlap: int,
        uploaded_by: str,
    ) -> dict[str, Any]:
        from app.core.config import get_settings

        container = get_container()
        filename = _safe_filename(filename)
        max_bytes = get_settings().max_upload_bytes
        if len(data) > max_bytes:
            raise ValueError(f"File exceeds max upload size ({max_bytes} bytes)")

        file_hash = sha256_bytes(data)

        # File-level dedupe: block re-upload of identical bytes while active
        with db_manager.session(DatabaseKind.RAG) as session:
            existing = (
                session.query(RagDocument)
                .filter(
                    RagDocument.file_hash == file_hash,
                    RagDocument.deleted_at.is_(None),
                )
                .first()
            )
            if existing:
                raise DuplicateDocumentError(existing.doc_id, file_hash)

        doc_id = f"DOC-{uuid.uuid4().hex[:10].upper()}"
        storage_key = f"{doc_id}/{filename}"

        ext = Path(filename).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file type '{ext}'. Allowed uploads: pdf, txt, md, docx, csv"
            )

        container.storage.save(storage_key, data, content_type)
        absolute_path = container.storage.resolve_path_or_url(storage_key)

        loaded = load_uploaded_document(absolute_path)
        strategy = get_chunking_strategy(
            chunk_strategy,
            embedding=container.embedding,
            llm=container.llm_for("chunking"),
        )
        chunks = strategy.split(
            loaded.text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            pages=loaded.pages,
        )

        # Existing active chunk hashes → skip vector upsert for duplicates
        with db_manager.session(DatabaseKind.RAG) as session:
            active_doc_ids = {
                d.doc_id
                for d in session.query(RagDocument).filter(RagDocument.deleted_at.is_(None)).all()
            }
            existing_hash_rows = (
                session.query(RagDocumentChunk.chunk_hash, RagDocumentChunk.chunk_id)
                .filter(
                    RagDocumentChunk.doc_id.in_(active_doc_ids) if active_doc_ids else False,
                    RagDocumentChunk.chunk_hash.isnot(None),
                    RagDocumentChunk.is_duplicate == 0,
                )
                .all()
                if active_doc_ids
                else []
            )
            existing_hashes = {h: cid for h, cid in existing_hash_rows if h}

        records: list[VectorRecord] = []
        chunk_rows: list[RagDocumentChunk] = []
        skipped_duplicates = 0
        seen_in_file: set[str] = set()

        for c in chunks:
            chunk_id = f"{doc_id}-{c.index}"
            chunk_hash = sha256_text(c.text.strip())

            # Dedupe within the same upload + against corpus
            duplicate_of = None
            is_dup = 0
            if chunk_hash in seen_in_file:
                is_dup = 1
                skipped_duplicates += 1
            elif chunk_hash in existing_hashes:
                is_dup = 1
                duplicate_of = existing_hashes[chunk_hash]
                skipped_duplicates += 1
            else:
                seen_in_file.add(chunk_hash)
                existing_hashes[chunk_hash] = chunk_id
                records.append(
                    VectorRecord(
                        id=chunk_id,
                        text=c.text,
                        metadata={
                            "doc_id": doc_id,
                            "title": title,
                            "chunk_index": c.index,
                            "page_number": c.page_number if c.page_number is not None else "",
                            "strategy": chunk_strategy,
                            "loader": loaded.loader_name,
                            "chunk_hash": chunk_hash,
                            "file_hash": file_hash,
                        },
                    )
                )

            chunk_rows.append(
                RagDocumentChunk(
                    doc_id=doc_id,
                    chunk_id=chunk_id,
                    chunk_index=c.index,
                    chunk_hash=chunk_hash,
                    text=c.text,
                    page_number=c.page_number,
                    token_estimate=c.token_estimate,
                    is_duplicate=is_dup,
                    duplicate_of_chunk_id=duplicate_of,
                )
            )

        if records:
            container.vector_store.upsert(records)
            container.vector_store.persist()

        self._rebuild_bm25_index()

        from app.core.config import get_settings

        settings = get_settings()
        indexed_count = len(records)
        with db_manager.session(DatabaseKind.RAG) as session:
            session.add(
                RagDocument(
                    doc_id=doc_id,
                    title=title,
                    source_type=source_type,
                    original_filename=filename,
                    storage_key=storage_key,
                    content_type=content_type,
                    file_hash=file_hash,
                    chunk_strategy=chunk_strategy,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                    chunk_count=indexed_count,
                    vector_store=settings.vector_store_provider,
                    embedding_provider=settings.embedding_provider,
                    status="indexed",
                    uploaded_by=uploaded_by,
                )
            )
            for row in chunk_rows:
                session.add(row)

        logger.info(
            "document_ingested",
            doc_id=doc_id,
            chunks=len(chunks),
            indexed=indexed_count,
            skipped_duplicates=skipped_duplicates,
            strategy=chunk_strategy,
            loader=loaded.loader_name,
            file_hash=file_hash[:16],
        )
        return {
            "doc_id": doc_id,
            "file_hash": file_hash,
            "chunk_count": indexed_count,
            "chunks_total": len(chunks),
            "chunks_skipped_duplicate": skipped_duplicates,
            "storage_key": storage_key,
            "loader": loaded.loader_name,
            "langchain_documents": len(loaded.documents),
        }

    def list_documents(self, include_deleted: bool = False) -> list[dict[str, Any]]:
        with db_manager.session(DatabaseKind.RAG) as session:
            q = session.query(RagDocument)
            if not include_deleted:
                q = q.filter(RagDocument.deleted_at.is_(None))
            docs = q.order_by(RagDocument.created_at.desc()).all()
            return [
                {
                    "doc_id": d.doc_id,
                    "title": d.title,
                    "source_type": d.source_type,
                    "original_filename": d.original_filename,
                    "file_hash": d.file_hash,
                    "chunk_strategy": d.chunk_strategy,
                    "chunk_size": d.chunk_size,
                    "chunk_overlap": d.chunk_overlap,
                    "chunk_count": d.chunk_count,
                    "status": d.status,
                    "uploaded_by": d.uploaded_by,
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                }
                for d in docs
            ]

    def get_document_bytes(self, doc_id: str) -> tuple[str, bytes, str]:
        with db_manager.session(DatabaseKind.RAG) as session:
            doc = (
                session.query(RagDocument)
                .filter(RagDocument.doc_id == doc_id, RagDocument.deleted_at.is_(None))
                .first()
            )
            if not doc:
                raise FileNotFoundError(doc_id)
            filename = doc.original_filename
            content_type = doc.content_type
            key = doc.storage_key
        data = get_container().storage.load(key)
        return filename, data, content_type

    def delete_document(self, doc_id: str, actor: str) -> dict[str, Any]:
        container = get_container()
        with db_manager.session(DatabaseKind.RAG) as session:
            doc = (
                session.query(RagDocument)
                .filter(RagDocument.doc_id == doc_id, RagDocument.deleted_at.is_(None))
                .first()
            )
            if not doc:
                raise FileNotFoundError(doc_id)
            storage_key = doc.storage_key

        # Remove retrieval artifacts first so a failed DB soft-delete cannot leave
        # searchable chunks for a "deleted" document.
        removed = container.vector_store.delete_by_doc_id(doc_id)
        storage_deleted = container.storage.delete(storage_key)

        with db_manager.session(DatabaseKind.RAG) as session:
            doc = (
                session.query(RagDocument)
                .filter(RagDocument.doc_id == doc_id, RagDocument.deleted_at.is_(None))
                .first()
            )
            if doc:
                doc.status = "deleted"
                doc.deleted_at = datetime.utcnow()
                session.query(RagDocumentChunk).filter(RagDocumentChunk.doc_id == doc_id).delete()

        self._rebuild_bm25_index()
        logger.info(
            "document_deleted",
            doc_id=doc_id,
            vector_removed=removed,
            storage_deleted=storage_deleted,
            actor=actor,
        )
        return {
            "doc_id": doc_id,
            "vector_chunks_removed": removed,
            "storage_deleted": bool(storage_deleted),
        }

    def _rebuild_bm25_index(self) -> None:
        container = get_container()
        with db_manager.session(DatabaseKind.RAG) as session:
            active_docs = {
                d.doc_id
                for d in session.query(RagDocument).filter(RagDocument.deleted_at.is_(None)).all()
            }
            rows = session.query(RagDocumentChunk).all()
            # Only non-duplicate chunks from active docs feed BM25
            rows = [r for r in rows if r.doc_id in active_docs and not getattr(r, "is_duplicate", 0)]
            texts = [r.text for r in rows]
            ids = [r.chunk_id for r in rows]
            metas = [{"doc_id": r.doc_id, "chunk_index": r.chunk_index} for r in rows]
        container.rag.rebuild_bm25(texts, ids, metas)

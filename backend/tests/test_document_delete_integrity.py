"""Document delete must remove storage object + vector entries + rag chunk rows."""

from __future__ import annotations

import uuid

from app.core.container import get_container
from app.db.models.rag import RagDocument, RagDocumentChunk
from app.db.session import DatabaseKind, db_manager
from app.services.document_service import DocumentService


def setup_module():
    db_manager.init()


def test_delete_document_removes_storage_vectors_and_chunks():
    svc = DocumentService()
    marker = uuid.uuid4().hex
    payload = (
        f"Fictional packaging quarantine SOP for unit test {marker}.\n"
        "Quarantine affected LOT material within 24 hours.\n"
    ).encode("utf-8")
    ingested = svc.ingest(
        title="Delete Integrity SOP",
        source_type="sop",
        filename=f"delete-integrity-{marker}.txt",
        content_type="text/plain",
        data=payload,
        chunk_strategy="recursive",
        chunk_size=256,
        chunk_overlap=32,
        uploaded_by="admin",
    )
    doc_id = ingested["doc_id"]
    storage_key = ingested["storage_key"]
    container = get_container()

    assert container.storage.exists(storage_key)
    with db_manager.session(DatabaseKind.RAG) as session:
        chunks_before = (
            session.query(RagDocumentChunk).filter(RagDocumentChunk.doc_id == doc_id).count()
        )
    assert chunks_before >= 1

    result = svc.delete_document(doc_id, actor="admin")
    assert result["doc_id"] == doc_id
    assert result["storage_deleted"] is True
    assert not container.storage.exists(storage_key)

    with db_manager.session(DatabaseKind.RAG) as session:
        chunks_after = (
            session.query(RagDocumentChunk).filter(RagDocumentChunk.doc_id == doc_id).count()
        )
        doc = session.query(RagDocument).filter(RagDocument.doc_id == doc_id).first()
        assert chunks_after == 0
        assert doc is not None
        assert doc.deleted_at is not None
        assert doc.status == "deleted"

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pathlib import Path

from pydantic import BaseModel, Field

from app.auth.deps import require_permission
from app.core.container import get_container
from app.core.config import get_settings
from app.db.models.core import User
from app.modules.chunking.strategies import list_chunking_strategies
from app.services.chat_service import ChatHistoryService
from app.services.document_service import DocumentService, DuplicateDocumentError

router = APIRouter(prefix="/rag", tags=["rag"])
docs = DocumentService()
chat_svc = ChatHistoryService()


class RagQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    top_n: int = Field(default=5, ge=1, le=20)
    session_id: str | None = None


class RagSessionCreate(BaseModel):
    title: str | None = None


@router.get("/chunk-strategies")
def chunk_strategies(user: User = Depends(require_permission("rag:view"))):
    settings = get_settings()
    return {
        "strategies": list_chunking_strategies(),
        "defaults": {
            "strategy": settings.default_chunk_strategy,
            "chunk_size": settings.default_chunk_size,
            "chunk_overlap": settings.default_chunk_overlap,
        },
        "supported_upload_types": [".pdf", ".txt", ".md", ".docx", ".csv"],
        "loaders": {
            ".pdf": "PyPDFLoader",
            ".txt": "TextLoader",
            ".md": "TextLoader",
            ".docx": "Docx2txtLoader",
            ".csv": "CSVLoader",
        },
        "strategy_notes": {
            "recursive": "LangChain RecursiveCharacterTextSplitter",
            "semantic": "Uses configured EMBEDDING_PROVIDER (cosine breakpoints between sentences)",
            "structure_aware": "Splits on headings/sections then packs",
            "agentic": "Uses LLM_CHUNKING_* (falls back to LLM_PROVIDER) to propose topic segments as JSON",
            "page_based": "One unit per PDF page / loader document then packs",
        },
        "active_providers": {
            "embedding_provider": settings.embedding_provider,
            "llm_provider": settings.llm_provider,
            "llm_roles": settings.llm_roles_summary(),
        },
    }


@router.post("/documents")
async def upload_document(
    title: str = Form(...),
    source_type: str = Form("SOP"),
    chunk_strategy: str = Form("recursive"),
    chunk_size: int = Form(512),
    chunk_overlap: int = Form(64),
    file: UploadFile = File(...),
    user: User = Depends(require_permission("rag:upload")),
):
    data = await file.read()
    try:
        return docs.ingest(
            title=title,
            source_type=source_type,
            filename=file.filename or "upload.bin",
            content_type=file.content_type or "application/octet-stream",
            data=data,
            chunk_strategy=chunk_strategy,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            uploaded_by=user.username,
        )
    except DuplicateDocumentError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "existing_doc_id": exc.existing_doc_id,
                "file_hash": exc.file_hash,
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/documents")
def list_documents(user: User = Depends(require_permission("rag:view"))):
    return docs.list_documents()


@router.get("/documents/{doc_id}/content")
def view_document(doc_id: str, user: User = Depends(require_permission("rag:view"))):
    try:
        filename, data, content_type = docs.get_document_bytes(doc_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc
    safe_name = Path(filename.replace("\\", "/")).name.replace('"', "")
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{safe_name}"'},
    )


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: str, user: User = Depends(require_permission("rag:delete"))):
    try:
        return docs.delete_document(doc_id, actor=user.username)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc


@router.post("/sessions")
def create_rag_session(
    payload: RagSessionCreate,
    user: User = Depends(require_permission("rag:query")),
):
    return chat_svc.create_session(user.username, title=payload.title, session_kind="rag")


@router.get("/sessions")
def list_rag_sessions(user: User = Depends(require_permission("rag:query"))):
    return chat_svc.list_sessions(user.username, session_kind="rag")


@router.delete("/sessions/{session_id}")
def delete_rag_session(session_id: str, user: User = Depends(require_permission("rag:query"))):
    try:
        chat_svc.soft_delete_session(session_id, user.username)
        return {"ok": True}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc


@router.get("/sessions/{session_id}/messages")
def list_rag_messages(session_id: str, user: User = Depends(require_permission("rag:query"))):
    try:
        return chat_svc.list_messages(session_id, user.username)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc


@router.post("/query")
def rag_query(payload: RagQueryRequest, user: User = Depends(require_permission("rag:query"))):
    # ensure BM25 is warm
    docs._rebuild_bm25_index()
    container = get_container()
    result = container.rag.query(
        payload.question, actor=user.username, role=user.role, top_n=payload.top_n
    )

    session_id = payload.session_id
    if session_id:
        try:
            chat_svc.get_session(session_id, username=user.username)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="RAG session not found") from exc
        chat_svc.add_message(
            session_id=session_id,
            username=user.username,
            role="user",
            content=payload.question,
            intent="rag",
        )
        answer = result.get("answer") or ""
        meta: dict[str, Any] = {
            "sources": result.get("sources"),
            "query_expansion": result.get("query_expansion"),
            "diagnostics": result.get("diagnostics"),
        }
        chat_svc.add_message(
            session_id=session_id,
            username=user.username,
            role="assistant",
            content=answer,
            intent="rag",
            metadata=meta,
        )
        result = {**result, "session_id": session_id}
    return result


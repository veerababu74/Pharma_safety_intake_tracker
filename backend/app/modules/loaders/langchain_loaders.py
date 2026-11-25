"""LangChain document loaders for admin uploads (PDF, TXT, DOCX, CSV)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.documents import Document

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx", ".csv"}


@dataclass
class LoadedDocument:
    """Normalized output for chunking + indexing."""

    text: str
    pages: list[str]
    documents: list[Document]
    loader_name: str
    metadata: dict[str, Any]


def _extension(path: str | Path) -> str:
    return Path(path).suffix.lower()


def _build_loader(file_path: str):
    """Factory: pick the right LangChain loader from file extension."""
    ext = _extension(file_path)

    if ext == ".pdf":
        from langchain_community.document_loaders import PyPDFLoader

        return PyPDFLoader(file_path), "PyPDFLoader"

    if ext in {".txt", ".md"}:
        from langchain_community.document_loaders import TextLoader

        return TextLoader(file_path, encoding="utf-8"), "TextLoader"

    if ext == ".docx":
        from langchain_community.document_loaders import Docx2txtLoader

        return Docx2txtLoader(file_path), "Docx2txtLoader"

    if ext == ".csv":
        from langchain_community.document_loaders import CSVLoader

        # Each row becomes a Document — good for solution/knowledge CSVs
        return (
            CSVLoader(
                file_path=file_path,
                encoding="utf-8",
                csv_args={"delimiter": ","},
            ),
            "CSVLoader",
        )

    raise ValueError(
        f"Unsupported file type '{ext}'. Allowed: {sorted(SUPPORTED_EXTENSIONS)}"
    )


def load_uploaded_document(file_path: str | Path) -> LoadedDocument:
    """
    Load an uploaded file using LangChain loaders.

    Returns combined text, page/row texts (for page_based chunking),
    and raw LangChain Document objects.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Upload file not found: {path}")

    ext = _extension(path)
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext}'. Allowed: pdf, txt, md, docx, csv"
        )

    loader, loader_name = _build_loader(str(path))
    docs: list[Document] = loader.load()
    if not docs:
        raise ValueError(f"LangChain {loader_name} produced no content from {path.name}")

    pages: list[str] = []
    for doc in docs:
        content = (doc.page_content or "").strip()
        if content:
            pages.append(content)

    if not pages:
        raise ValueError(f"No extractable text found in {path.name}")

    text = "\n\n".join(pages)
    meta: dict[str, Any] = {
        "source": str(path),
        "loader": loader_name,
        "document_count": len(docs),
    }
    # Preserve first doc metadata hints (page, row, source, etc.)
    if docs[0].metadata:
        meta.update({k: v for k, v in docs[0].metadata.items() if k not in meta})

    return LoadedDocument(
        text=text,
        pages=pages,
        documents=docs,
        loader_name=loader_name,
        metadata=meta,
    )

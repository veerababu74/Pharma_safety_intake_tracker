"""
Index NovaCure sample knowledge files into ChromaDB (+ BM25 / rag.db metadata).

Run from the repo (uses backend venv + backend/.env):

  cd backend
  .\\.venv\\Scripts\\activate
  python ..\\sample_data\\index_to_chromadb.py

What it does:
  1. Forces VECTOR_STORE_PROVIDER=chromadb for this process
  2. Loads app DocumentService (chunk → embed → Chroma upsert → BM25 rebuild)
  3. Ingests the long SOP pack under sample_data/txt|pdf|docx (SOP-*-10*.*)

After indexing, restart the API with VECTOR_STORE_PROVIDER=chromadb in backend/.env
so Knowledge Query / Agent RAG hit the same Chroma collection.
"""
from __future__ import annotations

import mimetypes
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
SAMPLE = Path(__file__).resolve().parent

# Prefer Chroma for this indexing run (overrides .env for the process)
os.environ["VECTOR_STORE_PROVIDER"] = "chromadb"

# Make `app` importable
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from app.core.container import get_container  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402
from app.db.session import db_manager  # noqa: E402
from app.services.document_service import DocumentService, DuplicateDocumentError  # noqa: E402

# Clear caches so chromadb env override is picked up
if hasattr(get_settings, "cache_clear"):
    get_settings.cache_clear()
get_container.cache_clear()
setup_logging()
settings = get_settings()
db_manager.init()

CONTENT_TYPES = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".csv": "text/csv",
}

# Long demo pack (3 stems × 3 formats). Add short legacy SOPs if you want more coverage.
DEFAULT_GLOBS = [
    "txt/SOP-*-10*.txt",
    "pdf/SOP-*-10*.pdf",
    "docx/SOP-*-10*.docx",
    "txt/GOLD-FACT-SHEET-*.txt",
    "txt/PAST-REPORT-DIGEST-*.txt",
]


def collect_files() -> list[Path]:
    files: list[Path] = []
    for pattern in DEFAULT_GLOBS:
        files.extend(sorted(SAMPLE.glob(pattern)))
    # de-dupe while preserving order
    seen: set[Path] = set()
    out: list[Path] = []
    for f in files:
        if f.is_file() and f not in seen:
            seen.add(f)
            out.append(f)
    return out


def main() -> int:
    print("=== NovaCure sample → ChromaDB indexer ===")
    print(f"Backend:     {BACKEND}")
    print(f"Provider:    {settings.vector_store_provider} (expected chromadb)")
    print(f"Chroma dir:  {settings.chroma_dir}")
    print(f"Upload dir:  {settings.upload_dir}")

    if settings.vector_store_provider != "chromadb":
        print(
            "WARNING: settings.vector_store_provider is not chromadb. "
            "Set VECTOR_STORE_PROVIDER=chromadb in backend/.env and re-run."
        )

    container = get_container()
    print(f"Vector store class: {container.vector_store.__class__.__name__}")

    files = collect_files()
    if not files:
        print("No sample files found. Generate them first:")
        print("  python sample_data/_generate_knowledge_docs.py")
        return 1

    svc = DocumentService()
    ok = 0
    skipped = 0
    failed = 0

    for path in files:
        ext = path.suffix.lower()
        ctype = CONTENT_TYPES.get(ext) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        data = path.read_bytes()
        title = path.stem.replace("-", " ")
        try:
            result = svc.ingest(
                title=title,
                source_type=ext.lstrip("."),
                filename=path.name,
                content_type=ctype,
                data=data,
                chunk_strategy=settings.default_chunk_strategy,
                chunk_size=settings.default_chunk_size,
                chunk_overlap=settings.default_chunk_overlap,
                uploaded_by="indexer-script",
            )
            print(
                f"OK  {path.name} → {result.get('doc_id')} "
                f"({result.get('chunk_count')} chunks stored, "
                f"parsed={result.get('chunks_total')}, "
                f"dup_skipped={result.get('chunks_skipped_duplicate', 0)}, "
                f"loader={result.get('loader')})"
            )
            ok += 1
        except DuplicateDocumentError as exc:
            print(f"SKIP {path.name} — already indexed as {exc.existing_doc_id}")
            skipped += 1
        except Exception as exc:  # noqa: BLE001 — show each file failure and continue
            print(f"FAIL {path.name} — {type(exc).__name__}: {exc}")
            failed += 1

    print("---")
    print(f"Done. indexed={ok} skipped={skipped} failed={failed}")
    print("Next: ensure backend/.env has VECTOR_STORE_PROVIDER=chromadb, then restart uvicorn.")
    print("Ask in Knowledge Query: What should we do for a packaging complaint on LOT-88392?")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

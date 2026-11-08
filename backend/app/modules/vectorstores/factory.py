"""Vector store factory using LangChain FAISS / Chroma adapters."""

from __future__ import annotations

from app.core.config import get_settings
from app.modules.embeddings.base import EmbeddingProvider
from app.modules.vectorstores.base import VectorStore

_REGISTRY = ("faiss", "chromadb")


def create_vector_store(embedding: EmbeddingProvider) -> VectorStore:
    settings = get_settings()
    provider = settings.vector_store_provider

    if provider == "faiss":
        from app.modules.vectorstores.faiss_store import FaissVectorStore

        return FaissVectorStore(directory=settings.faiss_dir, embedding=embedding)

    if provider == "chromadb":
        from app.modules.vectorstores.chroma_store import ChromaVectorStore

        return ChromaVectorStore(directory=settings.chroma_dir, embedding=embedding)

    raise ValueError(
        f"Unsupported vector store provider: {provider}. Available: {list(_REGISTRY)}"
    )

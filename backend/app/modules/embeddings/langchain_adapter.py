"""Adapt our EmbeddingProvider to LangChain Embeddings interface."""

from __future__ import annotations

from langchain_core.embeddings import Embeddings

from app.modules.embeddings.base import EmbeddingProvider


class LangChainEmbeddingsAdapter(Embeddings):
    """Bridge so LangChain FAISS/Chroma can reuse our pluggable embedders."""

    def __init__(self, provider: EmbeddingProvider) -> None:
        self.provider = provider

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.provider.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self.provider.embed_query(text)

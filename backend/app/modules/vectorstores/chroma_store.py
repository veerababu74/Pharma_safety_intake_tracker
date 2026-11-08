"""LangChain Chroma vector store adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_community.vectorstores import Chroma

from app.modules.embeddings.base import EmbeddingProvider
from app.modules.embeddings.langchain_adapter import LangChainEmbeddingsAdapter
from app.modules.vectorstores.base import VectorRecord, VectorSearchHit, VectorStore


class ChromaVectorStore(VectorStore):
    """Thin wrapper around ``langchain_community.vectorstores.Chroma``."""

    name = "chromadb"

    def __init__(
        self,
        directory: str,
        embedding: EmbeddingProvider,
        collection_name: str = "pharma_rag",
    ) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lc_embeddings = LangChainEmbeddingsAdapter(embedding)
        self.store = Chroma(
            collection_name=collection_name,
            embedding_function=self._lc_embeddings,
            persist_directory=str(self.directory),
        )

    def upsert(self, records: list[VectorRecord]) -> None:
        if not records:
            return

        texts = [r.text for r in records]
        ids = [r.id for r in records]
        metadatas: list[dict[str, Any]] = []
        for r in records:
            meta = dict(r.metadata or {})
            meta["chunk_id"] = r.id
            cleaned = {k: ("" if v is None else v) for k, v in meta.items()}
            metadatas.append(cleaned)

        self.store.add_texts(texts=texts, metadatas=metadatas, ids=ids)
        self.persist()

    def similarity_search(self, embedding: list[float], top_k: int = 50) -> list[VectorSearchHit]:
        # LangChain Chroma vector search
        docs = self.store.similarity_search_by_vector(embedding, k=top_k)
        hits: list[VectorSearchHit] = []
        for rank, doc in enumerate(docs, start=1):
            meta = dict(doc.metadata or {})
            chunk_id = str(meta.get("chunk_id") or "")
            # Chroma similarity_search_by_vector does not always return scores;
            # use rank-based descending score for RRF fusion compatibility.
            score = 1.0 / rank
            hits.append(
                VectorSearchHit(
                    id=chunk_id or (doc.id or ""),
                    text=doc.page_content,
                    score=float(score),
                    metadata=meta,
                )
            )

        # Prefer scored API when available
        try:
            scored = self.store.similarity_search_with_score_by_vector(embedding, k=top_k)
            scored_hits: list[VectorSearchHit] = []
            for doc, distance in scored:
                meta = dict(doc.metadata or {})
                chunk_id = str(meta.get("chunk_id") or "")
                # Chroma often returns distance; convert to similarity-ish score
                score = 1.0 / (1.0 + float(distance))
                scored_hits.append(
                    VectorSearchHit(
                        id=chunk_id or (doc.id or ""),
                        text=doc.page_content,
                        score=score,
                        metadata=meta,
                    )
                )
            if scored_hits:
                return scored_hits
        except Exception:
            pass

        return hits

    def delete_by_doc_id(self, doc_id: str) -> int:
        # LangChain Chroma exposes underlying collection
        collection = self.store._collection  # noqa: SLF001 — intentional adapter access
        existing = collection.get(where={"doc_id": doc_id})
        ids = existing.get("ids") or []
        if not ids:
            return 0
        self.store.delete(ids=ids)
        self.persist()
        return len(ids)

    def persist(self) -> None:
        # PersistentClient-backed LangChain Chroma auto-persists; keep method for interface.
        persist_fn = getattr(self.store, "persist", None)
        if callable(persist_fn):
            persist_fn()

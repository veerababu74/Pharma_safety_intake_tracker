"""LangChain FAISS vector store adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

from app.modules.embeddings.base import EmbeddingProvider
from app.modules.embeddings.langchain_adapter import LangChainEmbeddingsAdapter
from app.modules.vectorstores.base import VectorRecord, VectorSearchHit, VectorStore


class FaissVectorStore(VectorStore):
    """Thin wrapper around ``langchain_community.vectorstores.FAISS``."""

    name = "faiss"

    def __init__(self, directory: str, embedding: EmbeddingProvider) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._embedding_provider = embedding
        self._lc_embeddings = LangChainEmbeddingsAdapter(embedding)
        self._index_name = "index"
        self.store = self._load_or_create()

    def _index_exists(self) -> bool:
        return (self.directory / f"{self._index_name}.faiss").exists() and (
            self.directory / f"{self._index_name}.pkl"
        ).exists()

    def _load_or_create(self) -> FAISS:
        if self._index_exists():
            return FAISS.load_local(
                folder_path=str(self.directory),
                embeddings=self._lc_embeddings,
                index_name=self._index_name,
                allow_dangerous_deserialization=True,
            )

        # Bootstrap empty FAISS index the LangChain way (IndexFlatL2)
        import faiss

        dim = self._embedding_provider.dimension
        index = faiss.IndexFlatL2(dim)
        return FAISS(
            embedding_function=self._lc_embeddings,
            index=index,
            docstore=InMemoryDocstore({}),
            index_to_docstore_id={},
        )

    def upsert(self, records: list[VectorRecord]) -> None:
        if not records:
            return

        texts = [r.text for r in records]
        metadatas: list[dict[str, Any]] = []
        for r in records:
            meta = dict(r.metadata or {})
            # keep chunk id in metadata for reliable delete/search mapping
            meta["chunk_id"] = r.id
            # LangChain/Chroma-safe: avoid None values
            cleaned = {k: ("" if v is None else v) for k, v in meta.items()}
            metadatas.append(cleaned)
        ids = [r.id for r in records]

        # Prefer LangChain text ingest (it embeds via our adapter).
        # If precomputed embeddings are supplied, still use texts path for simplicity/consistency.
        self.store.add_texts(texts=texts, metadatas=metadatas, ids=ids)
        self.persist()

    def similarity_search(self, embedding: list[float], top_k: int = 50) -> list[VectorSearchHit]:
        if getattr(self.store, "index", None) is None or self.store.index.ntotal == 0:
            return []

        k = min(top_k, self.store.index.ntotal)
        # LangChain FAISS: vector search with scores
        results = self.store.similarity_search_with_score_by_vector(embedding, k=k)
        hits: list[VectorSearchHit] = []
        for doc, distance in results:
            meta = dict(doc.metadata or {})
            chunk_id = str(meta.get("chunk_id") or meta.get("id") or "")
            # LangChain FAISS returns L2 distance (lower=better) → similarity-ish
            similarity = 1.0 / (1.0 + float(distance))
            hits.append(
                VectorSearchHit(
                    id=chunk_id or doc.id or "",
                    text=doc.page_content,
                    score=similarity,
                    metadata=meta,
                )
            )
        return hits

    def delete_by_doc_id(self, doc_id: str) -> int:
        # Collect matching ids from LangChain docstore
        to_delete: list[str] = []
        docstore = self.store.docstore
        id_map = getattr(self.store, "index_to_docstore_id", {}) or {}
        for _idx, doc_key in list(id_map.items()):
            document = docstore.search(doc_key)
            if not isinstance(document, Document):
                continue
            meta = document.metadata or {}
            if str(meta.get("doc_id")) == str(doc_id):
                to_delete.append(str(doc_key))

        if not to_delete:
            return 0

        self.store.delete(ids=to_delete)
        self.persist()
        return len(to_delete)

    def persist(self) -> None:
        self.store.save_local(folder_path=str(self.directory), index_name=self._index_name)

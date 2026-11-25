"""Rerankers for hybrid RAG: CrossEncoder (best) → embedding cosine → lexical."""

from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any

import numpy as np

from app.core.logging import get_logger
from app.modules.embeddings.base import EmbeddingProvider

logger = get_logger("reranker")


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9\-]+", text.lower())


class Reranker(ABC):
    name: str

    @abstractmethod
    def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_n: int = 5,
        score_threshold: float = 0.40,
    ) -> list[dict[str, Any]]:
        """
        candidates items: {chunk_id, text, score, metadata}
        returns same shape with updated score, sorted desc, filtered.
        """


class LexicalReranker(Reranker):
    name = "lexical"

    def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_n: int = 5,
        score_threshold: float = 0.40,
    ) -> list[dict[str, Any]]:
        q_tokens = set(_tokenize(query))
        scored: list[dict[str, Any]] = []
        for c in candidates:
            c_tokens = set(_tokenize(c.get("text", "")))
            if not c_tokens:
                continue
            overlap = len(q_tokens & c_tokens) / max(1, len(q_tokens))
            prior = float(c.get("score") or 0.0)
            score = 0.7 * overlap + 0.3 * (1 / (1 + math.exp(-8 * prior)))
            item = dict(c)
            item["score"] = score
            item["rerank_method"] = self.name
            scored.append(item)
        scored.sort(key=lambda x: x["score"], reverse=True)
        filtered = [c for c in scored if c["score"] >= score_threshold] or scored[:top_n]
        return filtered[:top_n]


class EmbeddingCosineReranker(Reranker):
    """Bi-encoder style rerank: cosine(query, chunk) using configured embeddings."""

    name = "embedding_cosine"

    def __init__(self, embedding: EmbeddingProvider) -> None:
        self.embedding = embedding

    def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_n: int = 5,
        score_threshold: float = 0.40,
    ) -> list[dict[str, Any]]:
        if not candidates:
            return []
        q = np.array(self.embedding.embed_query(query), dtype=np.float32)
        q = q / (np.linalg.norm(q) + 1e-9)
        texts = [c.get("text", "") for c in candidates]
        docs = np.array(self.embedding.embed_documents(texts), dtype=np.float32)
        norms = np.linalg.norm(docs, axis=1, keepdims=True) + 1e-9
        docs = docs / norms
        sims = docs @ q
        scored: list[dict[str, Any]] = []
        for c, sim in zip(candidates, sims):
            item = dict(c)
            # blend with retrieval prior lightly
            prior = float(c.get("score") or 0.0)
            item["score"] = float(0.85 * sim + 0.15 * prior)
            item["rerank_method"] = self.name
            scored.append(item)
        scored.sort(key=lambda x: x["score"], reverse=True)
        filtered = [c for c in scored if c["score"] >= score_threshold] or scored[:top_n]
        return filtered[:top_n]


class CrossEncoderReranker(Reranker):
    """
    Best quality local reranker: sentence-transformers CrossEncoder
    (e.g. cross-encoder/ms-marco-MiniLM-L-6-v2).
    """

    name = "cross_encoder"

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> None:
        from app.modules.embeddings.model_cache import get_cross_encoder

        self.model_name = model_name
        # Same on-disk Hub cache + process singleton as embedding models.
        self.model = get_cross_encoder(model_name)

    def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_n: int = 5,
        score_threshold: float = 0.40,
    ) -> list[dict[str, Any]]:
        if not candidates:
            return []
        pairs = [(query, c.get("text", "")) for c in candidates]
        raw_scores = self.model.predict(pairs)
        # Normalize roughly to 0..1 via sigmoid for thresholding
        scored: list[dict[str, Any]] = []
        for c, raw in zip(candidates, raw_scores):
            raw_f = float(raw)
            norm = 1.0 / (1.0 + math.exp(-raw_f))
            item = dict(c)
            item["score"] = norm
            item["raw_cross_encoder_score"] = raw_f
            item["rerank_method"] = self.name
            scored.append(item)
        scored.sort(key=lambda x: x["score"], reverse=True)
        filtered = [c for c in scored if c["score"] >= score_threshold] or scored[:top_n]
        return filtered[:top_n]


@lru_cache
def _try_cross_encoder(model_name: str) -> CrossEncoderReranker | None:
    try:
        return CrossEncoderReranker(model_name=model_name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cross_encoder_unavailable", error=str(exc), model=model_name)
        return None


def create_reranker(
    *,
    provider: str,
    embedding: EmbeddingProvider,
    model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
) -> Reranker:
    """
    provider:
      - cross_encoder (preferred)
      - embedding
      - lexical
      - auto: cross_encoder → embedding → lexical
    """
    key = (provider or "auto").lower()
    if key == "lexical":
        return LexicalReranker()
    if key == "embedding":
        return EmbeddingCosineReranker(embedding)
    if key == "cross_encoder":
        ce = _try_cross_encoder(model_name)
        if ce is None:
            logger.warning("cross_encoder_fallback_to_embedding")
            return EmbeddingCosineReranker(embedding)
        return ce
    # auto
    ce = _try_cross_encoder(model_name)
    if ce is not None:
        return ce
    try:
        return EmbeddingCosineReranker(embedding)
    except Exception:
        return LexicalReranker()

"""Concrete embedding providers."""

from __future__ import annotations

import hashlib
from typing import Sequence

import numpy as np

from app.core.config import get_settings
from app.modules.embeddings.base import EmbeddingProvider


class HashEmbeddingProvider(EmbeddingProvider):
    """Deterministic local fallback when external models/keys unavailable."""

    name = "hash_fallback"

    def __init__(self, dim: int = 384) -> None:
        self._dim = dim

    @property
    def dimension(self) -> int:
        return self._dim

    def _embed_one(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        rng = np.random.default_rng(int.from_bytes(digest[:8], "little"))
        vec = rng.standard_normal(self._dim).astype(np.float32)
        vec = vec / (np.linalg.norm(vec) + 1e-9)
        return vec.tolist()

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)


class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    name = "sentence_transformers"

    def __init__(self, model_name: str) -> None:
        from app.modules.embeddings.model_cache import get_sentence_transformer

        # Shared in-process handle; Hub weights live under embedding_cache_dir.
        self._model = get_sentence_transformer(model_name)
        self._dim = int(self._model.get_sentence_embedding_dimension())

    @property
    def dimension(self) -> int:
        return self._dim

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._model.encode(list(texts), normalize_embeddings=True).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self._model.encode([text], normalize_embeddings=True)[0].tolist()


class OpenAIEmbeddingProvider(EmbeddingProvider):
    name = "openai"

    def __init__(self, model_name: str, api_key: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model_name or "text-embedding-3-small"
        self._dim = 1536

    @property
    def dimension(self) -> int:
        return self._dim

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        resp = self._client.embeddings.create(model=self._model, input=list(texts))
        return [item.embedding for item in resp.data]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class GoogleEmbeddingProvider(EmbeddingProvider):
    name = "google"

    def __init__(self, model_name: str, api_key: str) -> None:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        self._model = model_name or "models/text-embedding-004"
        self._dim = 768
        self._genai = genai

    @property
    def dimension(self) -> int:
        return self._dim

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            result = self._genai.embed_content(model=self._model, content=text)
            out.append(list(result["embedding"]))
        return out

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def create_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    provider = settings.embedding_provider
    try:
        if provider in {"sentence_transformers", "huggingface"}:
            return SentenceTransformerEmbeddingProvider(settings.embedding_model_name)
        if provider == "openai":
            if not settings.openai_api_key:
                raise ValueError("OPENAI_API_KEY missing")
            return OpenAIEmbeddingProvider(settings.embedding_model_name, settings.openai_api_key)
        if provider == "google":
            if not settings.google_api_key:
                raise ValueError("GOOGLE_API_KEY missing")
            return GoogleEmbeddingProvider(settings.embedding_model_name, settings.google_api_key)
    except Exception:
        return HashEmbeddingProvider()
    return HashEmbeddingProvider()

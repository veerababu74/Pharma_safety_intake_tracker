"""Process-level + on-disk cache for local embedding / cross-encoder models.

Download Hub weights once into ``settings.embedding_cache_dir``, then reuse the
same in-memory ``SentenceTransformer`` / ``CrossEncoder`` for the process
lifetime (AppContainer is already a singleton via ``get_container``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("embedding_model_cache")

_ST_CACHE: dict[str, Any] = {}
_CE_CACHE: dict[str, Any] = {}


def embedding_cache_dir() -> Path:
    settings = get_settings()
    path = Path(settings.embedding_cache_dir or (Path.cwd() / "data" / "embedding_models"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_sentence_transformer(model_name: str | None = None) -> Any:
    """Load SentenceTransformer once per (model, cache_dir) in this process."""
    settings = get_settings()
    name = (model_name or settings.embedding_model_name or "all-MiniLM-L6-v2").strip()
    cache_dir = str(embedding_cache_dir())
    key = f"{name}|{cache_dir}"
    cached = _ST_CACHE.get(key)
    if cached is not None:
        return cached

    from sentence_transformers import SentenceTransformer

    logger.info("embedding_model_load", model=name, cache_dir=cache_dir)
    model = SentenceTransformer(name, cache_folder=cache_dir)
    _ST_CACHE[key] = model
    return model


def get_cross_encoder(model_name: str | None = None) -> Any:
    """Load CrossEncoder once per (model, cache_dir) in this process."""
    settings = get_settings()
    name = (model_name or settings.reranker_model_name or "cross-encoder/ms-marco-MiniLM-L-6-v2").strip()
    cache_dir = str(embedding_cache_dir())
    key = f"{name}|{cache_dir}"
    cached = _CE_CACHE.get(key)
    if cached is not None:
        return cached

    from sentence_transformers import CrossEncoder

    logger.info("cross_encoder_model_load", model=name, cache_dir=cache_dir)
    # CrossEncoder forwards cache_folder to the underlying HF snapshot when supported.
    try:
        model = CrossEncoder(name, cache_folder=cache_dir)
    except TypeError:
        model = CrossEncoder(name)
    _CE_CACHE[key] = model
    return model


def clear_embedding_model_cache() -> None:
    """Test helper — drop in-memory model handles (disk cache kept)."""
    _ST_CACHE.clear()
    _CE_CACHE.clear()

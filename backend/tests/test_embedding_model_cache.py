"""Local embedding models should load once per process from a fixed cache dir."""

from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings
from app.modules.embeddings import model_cache as mc


def test_embedding_cache_dir_under_project_data(tmp_path, monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("EMBEDDING_CACHE_DIR", str(tmp_path / "emb"))
    get_settings.cache_clear()
    path = mc.embedding_cache_dir()
    assert path == Path(tmp_path / "emb")
    assert path.is_dir()
    get_settings.cache_clear()


def test_sentence_transformer_singleton(monkeypatch):
    mc.clear_embedding_model_cache()
    sentinel = object()
    calls = {"n": 0}

    def fake_st(name, cache_folder=None):  # noqa: ANN001
        calls["n"] += 1
        return sentinel

    monkeypatch.setattr(mc, "_ST_CACHE", {})
    import sentence_transformers

    monkeypatch.setattr(sentence_transformers, "SentenceTransformer", fake_st)

    a = mc.get_sentence_transformer("all-MiniLM-L6-v2")
    b = mc.get_sentence_transformer("all-MiniLM-L6-v2")
    assert a is b is sentinel
    assert calls["n"] == 1
    mc.clear_embedding_model_cache()

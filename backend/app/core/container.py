"""Simple DI container wiring factories (composition root)."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import LLM_ROLES, LLMRole
from app.modules.embeddings.providers import create_embedding_provider
from app.modules.llms.base import LLMProvider
from app.modules.llms.instrumented import InstrumentedLLMProvider
from app.modules.llms.providers import create_llm_provider
from app.modules.rag.pipeline import HybridRAGPipeline
from app.modules.storage.factory import create_storage
from app.modules.tracing.factory import create_tracer
from app.modules.vectorstores.factory import create_vector_store


class AppContainer:
    def __init__(self) -> None:
        self.embedding = create_embedding_provider()
        self.vector_store = create_vector_store(self.embedding)
        # Per-task LLMs (same provider+model+key shares one client via cache)
        self._llms: dict[str, LLMProvider] = {
            role: InstrumentedLLMProvider(create_llm_provider(role), role=role)
            for role in LLM_ROLES
        }
        # Backward-compatible default
        self.llm = self._llms["default"]
        self.storage = create_storage()
        self.tracer = create_tracer()
        self.rag = HybridRAGPipeline(
            embedding=self.embedding,
            vector_store=self.vector_store,
            llm=self.llm_for("rag"),
            tracer=self.tracer,
            query_enhancer_llm=self.llm_for("query_enhancer"),
            query_rewrite_llm=self.llm_for("query_rewrite"),
        )

    def llm_for(self, role: LLMRole | str = "default") -> LLMProvider:
        key = (role or "default").strip().lower()
        return self._llms.get(key) or self.llm


@lru_cache
def get_container() -> AppContainer:
    return AppContainer()

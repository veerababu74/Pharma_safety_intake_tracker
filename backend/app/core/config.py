"""Central application settings (12-factor style)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]

LLMProviderName = Literal["openai", "groq", "google", "openrouter", "mistral", "mock"]
LLMRole = Literal[
    "default",
    "router",
    "response",
    "social",
    "rag",
    "query_enhancer",
    "query_rewrite",
    "chunking",
]
LLM_ROLES: tuple[LLMRole, ...] = (
    "default",
    "router",
    "response",
    "social",
    "rag",
    "query_enhancer",
    "query_rewrite",
    "chunking",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Pharma Safety Intake Tracker"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    secret_key: str = "dev-secret-change-me-novacure-training"
    access_token_expire_minutes: int = 480
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # When APP_ENV=production, demo users are skipped unless this is true
    seed_demo_users: bool = False
    max_upload_bytes: int = 15 * 1024 * 1024

    core_db_url: str = Field(default=f"sqlite:///{BACKEND_ROOT / 'data' / 'core.db'}")
    audit_db_url: str = Field(default=f"sqlite:///{BACKEND_ROOT / 'data' / 'audit.db'}")
    rag_db_url: str = Field(default=f"sqlite:///{BACKEND_ROOT / 'data' / 'rag.db'}")
    obs_db_url: str = Field(default=f"sqlite:///{BACKEND_ROOT / 'data' / 'observability.db'}")

    embedding_provider: Literal[
        "sentence_transformers", "huggingface", "openai", "google"
    ] = "sentence_transformers"
    embedding_model_name: str = "all-MiniLM-L6-v2"

    vector_store_provider: Literal["faiss", "chromadb"] = "faiss"

    # Default / fallback LLM (used when a role override is blank)
    llm_provider: LLMProviderName = "mock"
    llm_model_name: str = "llama-3.1-8b-instant"

    # Shared provider API keys (used unless a role sets its own *_API_KEY)
    openai_api_key: str = ""
    groq_api_key: str = ""
    # Comma-separated Groq keys for rotation across roles / rate-limit failover
    groq_api_keys: str = ""
    google_api_key: str = ""
    openrouter_api_key: str = ""
    mistral_api_key: str = ""

    # Model tiers (used when a role's MODEL is blank)
    llm_cheap_model: str = "openai/gpt-oss-20b"
    llm_quality_model: str = "openai/gpt-oss-120b"

    # After all Groq keys fail, fall back to this provider (typically google)
    llm_fallback_provider: str = "google"
    llm_fallback_model: str = "gemini-1.5-flash"
    llm_fallback_enabled: bool = True

    # --- Per-role LLM overrides (blank provider/model => fall back to LLM_*) ---
    # Router: cheap classifier (intent only)
    llm_router_provider: str = ""
    llm_router_model: str = ""
    llm_router_api_key: str = ""

    # Response: end-user drafting after tools
    llm_response_provider: str = ""
    llm_response_model: str = ""
    llm_response_api_key: str = ""

    # Social: greetings / help / chit-chat
    llm_social_provider: str = ""
    llm_social_model: str = ""
    llm_social_api_key: str = ""

    # RAG answer generation from retrieved context
    llm_rag_provider: str = ""
    llm_rag_model: str = ""
    llm_rag_api_key: str = ""

    # Query enhancer (single rewritten search query)
    llm_query_enhancer_provider: str = ""
    llm_query_enhancer_model: str = ""
    llm_query_enhancer_api_key: str = ""

    # Query rewrite / multi-query variants
    llm_query_rewrite_provider: str = ""
    llm_query_rewrite_model: str = ""
    llm_query_rewrite_api_key: str = ""

    # Agentic chunking during ingest
    llm_chunking_provider: str = ""
    llm_chunking_model: str = ""
    llm_chunking_api_key: str = ""

    tracing_mode: Literal["langfuse", "custom", "both", "off"] = "custom"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    # Prefer LANGFUSE_BASE_URL (Langfuse docs); LANGFUSE_HOST kept for compat
    langfuse_host: str = "https://cloud.langfuse.com"
    langfuse_base_url: str = ""

    storage_provider: Literal["local", "azure_blob", "s3", "gcs"] = "local"
    upload_dir: str = str(BACKEND_ROOT / "data" / "uploads")
    faiss_dir: str = str(BACKEND_ROOT / "data" / "faiss")
    chroma_dir: str = str(BACKEND_ROOT / "data" / "chroma")

    default_chunk_strategy: str = "recursive"
    default_chunk_size: int = 512
    default_chunk_overlap: int = 64

    # RAG query expansion: original + 1 enhanced + N multi ≈ 5 searches
    rag_query_enhancer_enabled: bool = True
    rag_multi_query_enabled: bool = True
    rag_multi_query_count: int = 3

    # Reranker: auto|cross_encoder|embedding|lexical
    reranker_provider: Literal["auto", "cross_encoder", "embedding", "lexical"] = "auto"
    reranker_model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    rerank_score_threshold: float = 0.40
    rerank_candidate_limit: int = 50

    # Agent tool execution: local tools.py vs FastMCP (mcp_server)
    agent_tool_backend: Literal["local", "mcp"] = "local"
    # inprocess = Client(mcp_server.server.mcp); http = Client(AGENT_MCP_URL)
    agent_mcp_transport: Literal["inprocess", "http"] = "inprocess"
    agent_mcp_url: str = "http://127.0.0.1:8765/mcp"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def provider_api_key(self, provider: str) -> str:
        """Shared key for a provider family (first Groq key if pool configured)."""
        mapping = {
            "openai": self.openai_api_key,
            "groq": (self.groq_api_key_pool()[0] if self.groq_api_key_pool() else ""),
            "google": self.google_api_key,
            "openrouter": self.openrouter_api_key,
            "mistral": self.mistral_api_key,
        }
        return (mapping.get(provider) or "").strip()

    def groq_api_key_pool(self) -> list[str]:
        """Ordered unique Groq keys from GROQ_API_KEYS + GROQ_API_KEY."""
        keys: list[str] = []
        for part in (self.groq_api_keys or "").split(","):
            k = part.strip()
            if k and k not in keys:
                keys.append(k)
        primary = (self.groq_api_key or "").strip()
        if primary and primary not in keys:
            keys.insert(0, primary)
        return keys

    def langfuse_endpoint(self) -> str:
        return (self.langfuse_base_url or self.langfuse_host or "").strip()

    def _tier_model_for_role(self, role_key: str) -> str:
        quality = {"default", "response", "rag"}
        if role_key in quality:
            return (self.llm_quality_model or self.llm_model_name or "").strip()
        return (self.llm_cheap_model or self.llm_model_name or "").strip()

    def preferred_groq_key_index(self, role_key: str) -> int:
        """Sticky key index per role so traffic spreads across the pool."""
        # Explicit slots so cheap + quality roles don't all collapse to 0
        slots = {
            "router": 0,
            "social": 1,
            "query_enhancer": 2,
            "query_rewrite": 0,
            "chunking": 1,
            "response": 2,
            "rag": 1,
            "default": 0,
        }
        idx = slots.get(role_key, abs(hash(role_key)) % 3)
        pool = self.groq_api_key_pool()
        if not pool:
            return 0
        return idx % len(pool)

    def resolve_llm_role(self, role: LLMRole | str = "default") -> dict[str, str]:
        """
        Resolve provider / model / api_key for a task role.

        Empty role overrides fall back to LLM_PROVIDER + cheap/quality model tiers.
        Role-specific API key wins; else preferred Groq pool key / shared provider key.
        """
        role_key = (role or "default").strip().lower()
        prefix = f"llm_{role_key}" if role_key != "default" else None

        if role_key == "default":
            role_provider = ""
            role_model = ""
            role_api_key = ""
        else:
            role_provider = (getattr(self, f"{prefix}_provider", "") or "").strip().lower()
            role_model = (getattr(self, f"{prefix}_model", "") or "").strip()
            role_api_key = (getattr(self, f"{prefix}_api_key", "") or "").strip()

        provider = role_provider or (self.llm_provider or "mock").strip().lower()
        if role_model:
            model = role_model
        elif provider == "groq":
            model = self._tier_model_for_role(role_key) or (self.llm_model_name or "").strip()
        else:
            model = (self.llm_model_name or "").strip()

        if role_api_key:
            api_key = role_api_key
        elif provider == "groq":
            pool = self.groq_api_key_pool()
            api_key = pool[self.preferred_groq_key_index(role_key)] if pool else ""
        else:
            api_key = self.provider_api_key(provider)

        return {
            "role": role_key,
            "provider": provider,
            "model": model,
            "api_key": api_key,
            "groq_key_index": str(self.preferred_groq_key_index(role_key)),
            "fallback_provider": (self.llm_fallback_provider or "").strip().lower(),
            "fallback_model": (self.llm_fallback_model or "").strip(),
            "fallback_enabled": "1" if self.llm_fallback_enabled else "0",
        }

    def llm_roles_summary(self) -> dict[str, dict[str, str]]:
        """Safe summary (no API keys) for /system/providers."""
        out: dict[str, dict[str, str]] = {}
        pool_n = len(self.groq_api_key_pool())
        for role in LLM_ROLES:
            cfg = self.resolve_llm_role(role)
            out[role] = {
                "provider": cfg["provider"],
                "model": cfg["model"],
                "api_key_configured": "yes" if cfg["api_key"] or cfg["provider"] == "mock" else "no",
                "groq_key_slot": cfg.get("groq_key_index", "0"),
                "groq_pool_size": str(pool_n),
                "fallback": (
                    f"{cfg['fallback_provider']}:{cfg['fallback_model']}"
                    if cfg.get("fallback_enabled") == "1"
                    else "off"
                ),
            }
        return out


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.faiss_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.chroma_dir).mkdir(parents=True, exist_ok=True)
    Path(BACKEND_ROOT / "data").mkdir(parents=True, exist_ok=True)
    Path(BACKEND_ROOT / "logs").mkdir(parents=True, exist_ok=True)
    return settings

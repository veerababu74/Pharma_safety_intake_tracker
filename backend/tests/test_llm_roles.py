"""Per-task LLM role resolution from settings."""

from app.core.config import Settings
from app.modules.llms.providers import _cache_key, clear_llm_cache, create_llm_provider


def test_role_falls_back_to_default():
    s = Settings(
        llm_provider="mock",
        llm_model_name="default-model",
        llm_router_provider="",
        llm_router_model="",
    )
    cfg = s.resolve_llm_role("router")
    assert cfg["provider"] == "mock"
    assert cfg["model"] == "default-model"


def test_role_override_provider_and_model():
    s = Settings(
        llm_provider="mock",
        llm_model_name="default-model",
        llm_rag_provider="openai",
        llm_rag_model="gpt-4o-mini",
        openai_api_key="sk-test",
    )
    cfg = s.resolve_llm_role("rag")
    assert cfg["provider"] == "openai"
    assert cfg["model"] == "gpt-4o-mini"
    assert cfg["api_key"] == "sk-test"


def test_role_specific_api_key_wins():
    s = Settings(
        llm_provider="groq",
        groq_api_key="shared-key",
        llm_response_provider="groq",
        llm_response_model="llama-3.1-8b-instant",
        llm_response_api_key="role-key",
    )
    cfg = s.resolve_llm_role("response")
    assert cfg["api_key"] == "role-key"


def test_same_config_reuses_cached_client():
    clear_llm_cache()
    a = create_llm_provider("router")
    b = create_llm_provider("router")
    assert a is b
    assert _cache_key("mock", "llama-3.1-8b-instant", "") == _cache_key(
        "mock", "llama-3.1-8b-instant", ""
    )


def test_llm_roles_summary_hides_secrets():
    s = Settings(openai_api_key="sk-secret", llm_rag_provider="openai", llm_rag_model="gpt-4o-mini")
    summary = s.llm_roles_summary()
    blob = str(summary)
    assert "sk-secret" not in blob
    assert summary["rag"]["api_key_configured"] == "yes"

from app.core.config import Settings


def test_groq_key_pool_and_role_slots():
    s = Settings(
        groq_api_key="k1",
        groq_api_keys="k1,k2,k3",
        llm_provider="groq",
        llm_cheap_model="openai/gpt-oss-20b",
        llm_quality_model="openai/gpt-oss-120b",
        llm_fallback_enabled=True,
        llm_fallback_provider="google",
        llm_fallback_model="gemini-1.5-flash",
        google_api_key="g-test",
    )
    assert s.groq_api_key_pool() == ["k1", "k2", "k3"]
    router = s.resolve_llm_role("router")
    rag = s.resolve_llm_role("rag")
    assert router["model"] == "openai/gpt-oss-20b"
    assert rag["model"] == "openai/gpt-oss-120b"
    assert router["api_key"] == "k1"  # slot 0
    assert rag["api_key"] == "k2"  # slot 1
    assert s.resolve_llm_role("response")["api_key"] == "k3"  # slot 2


def test_langfuse_base_url_alias():
    s = Settings(langfuse_base_url="https://cloud.langfuse.com", langfuse_host="https://ignored.example")
    assert s.langfuse_endpoint() == "https://cloud.langfuse.com"

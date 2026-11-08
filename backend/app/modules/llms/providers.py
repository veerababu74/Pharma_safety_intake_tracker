"""Concrete LLM providers + role-aware factory."""

from __future__ import annotations

import hashlib
from typing import Any

import httpx

from app.core.config import LLMRole, get_settings
from app.core.logging import get_logger
from app.modules.llms.base import LLMProvider, LLMResponse
from app.modules.llms.usage import (
    tokens_from_google_response,
    tokens_from_openai_response,
    tokens_from_usage_dict,
    with_estimated_tokens,
)

logger = get_logger("llm_providers")


def _pack_response(
    *,
    content: str,
    model: str,
    provider: str,
    prompt: str,
    system: str | None,
    raw: dict | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
) -> LLMResponse:
    in_tok, out_tok, total = with_estimated_tokens(
        prompt=prompt,
        system=system,
        content=content,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )
    return LLMResponse(
        content=content,
        model=model,
        provider=provider,
        raw=raw,
        input_tokens=in_tok,
        output_tokens=out_tok,
        total_tokens=total,
    )

# Reuse clients when provider+model+key match across roles
_LLM_CACHE: dict[str, LLMProvider] = {}


class MockLLMProvider(LLMProvider):
    name = "mock"

    def generate(self, prompt: str, system: str | None = None) -> LLMResponse:
        # Deterministic grounded-style response for offline demos/tests
        snippet = prompt[-500:]
        content = (
            "Based only on the provided training context, here is a concise answer.\n"
            "If the context is insufficient, treat this as insufficient evidence.\n\n"
            f"Context excerpt considered:\n{snippet}\n\n"
            "Reminder: this prototype does not assess causality, treatment, or regulatory reportability."
        )
        return _pack_response(
            content=content,
            model="mock-1",
            provider=self.name,
            prompt=prompt,
            system=system,
        )


class OpenAILLMProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model or "gpt-4o-mini"

    def generate(self, prompt: str, system: str | None = None) -> LLMResponse:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = self._client.chat.completions.create(model=self._model, messages=messages)
        content = resp.choices[0].message.content or ""
        prompt_t, completion_t, total_t = tokens_from_openai_response(resp)
        return _pack_response(
            content=content,
            model=self._model,
            provider=self.name,
            prompt=prompt,
            system=system,
            raw=resp.model_dump(),
            prompt_tokens=prompt_t,
            completion_tokens=completion_t,
            total_tokens=total_t,
        )


class GroqLLMProvider(LLMProvider):
    name = "groq"

    def __init__(self, api_key: str, model: str) -> None:
        from groq import Groq

        self._client = Groq(api_key=api_key)
        self._model = model or "llama-3.1-8b-instant"

    def generate(self, prompt: str, system: str | None = None) -> LLMResponse:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = self._client.chat.completions.create(model=self._model, messages=messages)
        content = resp.choices[0].message.content or ""
        prompt_t, completion_t, total_t = tokens_from_openai_response(resp)
        raw = resp.model_dump() if hasattr(resp, "model_dump") else None
        return _pack_response(
            content=content,
            model=self._model,
            provider=self.name,
            prompt=prompt,
            system=system,
            raw=raw,
            prompt_tokens=prompt_t,
            completion_tokens=completion_t,
            total_tokens=total_t,
        )


class GoogleLLMProvider(LLMProvider):
    name = "google"

    def __init__(self, api_key: str, model: str) -> None:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        self._model_name = model or "gemini-1.5-flash"
        self._model = genai.GenerativeModel(self._model_name)

    def generate(self, prompt: str, system: str | None = None) -> LLMResponse:
        full = f"{system}\n\n{prompt}" if system else prompt
        resp = self._model.generate_content(full)
        content = getattr(resp, "text", None) or str(resp)
        prompt_t, completion_t, total_t = tokens_from_google_response(resp)
        return _pack_response(
            content=content,
            model=self._model_name,
            provider=self.name,
            prompt=prompt,
            system=system,
            prompt_tokens=prompt_t,
            completion_tokens=completion_t,
            total_tokens=total_t,
        )


class OpenRouterLLMProvider(LLMProvider):
    name = "openrouter"

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model or "openai/gpt-4o-mini"

    def generate(self, prompt: str, system: str | None = None) -> LLMResponse:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self._model, "messages": messages},
            )
            resp.raise_for_status()
            data = resp.json()
        content = data["choices"][0]["message"]["content"]
        prompt_t, completion_t, total_t = tokens_from_usage_dict(data.get("usage"))
        return _pack_response(
            content=content,
            model=self._model,
            provider=self.name,
            prompt=prompt,
            system=system,
            raw=data,
            prompt_tokens=prompt_t,
            completion_tokens=completion_t,
            total_tokens=total_t,
        )


class MistralLLMProvider(LLMProvider):
    name = "mistral"

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model or "mistral-small-latest"

    def generate(self, prompt: str, system: str | None = None) -> LLMResponse:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self._model, "messages": messages},
            )
            resp.raise_for_status()
            data = resp.json()
        content = data["choices"][0]["message"]["content"]
        prompt_t, completion_t, total_t = tokens_from_usage_dict(data.get("usage"))
        return _pack_response(
            content=content,
            model=self._model,
            provider=self.name,
            prompt=prompt,
            system=system,
            raw=data,
            prompt_tokens=prompt_t,
            completion_tokens=completion_t,
            total_tokens=total_t,
        )


def _cache_key(provider: str, model: str, api_key: str) -> str:
    digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16] if api_key else "nokey"
    return f"{provider}|{model}|{digest}"


def _build_provider(
    provider: str,
    model: str,
    api_key: str,
    *,
    allow_mock: bool = True,
) -> LLMProvider | None:
    """
    Construct a concrete LLM client.

    When allow_mock=False (Groq pool / fallback chain), return None on failure
    so ResilientLLMProvider can rotate keys instead of silently answering via Mock.
    """
    try:
        if provider == "openai" and api_key:
            return OpenAILLMProvider(api_key, model)
        if provider == "groq" and api_key:
            return GroqLLMProvider(api_key, model)
        if provider == "google" and api_key:
            return GoogleLLMProvider(api_key, model)
        if provider == "openrouter" and api_key:
            return OpenRouterLLMProvider(api_key, model)
        if provider == "mistral" and api_key:
            return MistralLLMProvider(api_key, model)
        if provider == "mock":
            return MockLLMProvider()
    except Exception as exc:  # noqa: BLE001
        logger.warning("llm_provider_init_failed", provider=provider, model=model, error=str(exc))
        return MockLLMProvider() if allow_mock else None
    if provider != "mock":
        logger.warning(
            "llm_provider_missing_key_or_unknown",
            provider=provider,
            model=model,
            falling_back="mock" if allow_mock else "none",
        )
    return MockLLMProvider() if allow_mock else None


def create_llm_provider(role: LLMRole | str = "default") -> LLMProvider:
    """
    Build (or reuse) an LLM for a task role.

    Roles: default | router | response | social | rag |
           query_enhancer | query_rewrite | chunking

    For Groq: rotates across GROQ_API_KEYS (preferred slot first).
    On total Groq failure: optional Google (or configured) fallback.
    """
    from app.modules.llms.resilient import ResilientLLMProvider

    settings = get_settings()
    cfg = settings.resolve_llm_role(role)
    provider = cfg["provider"]
    model = cfg["model"]
    role_key = cfg["role"]
    cache_id = (
        f"{role_key}|{provider}|{model}|pool={len(settings.groq_api_key_pool())}"
        f"|fb={cfg.get('fallback_enabled')}:{cfg.get('fallback_provider')}"
    )
    cached = _LLM_CACHE.get(cache_id)
    if cached is not None:
        return cached

    primaries: list[LLMProvider] = []
    if provider == "groq":
        pool = settings.groq_api_key_pool()
        if pool:
            start = settings.preferred_groq_key_index(role_key)
            ordered = pool[start:] + pool[:start]
            for api_key in ordered:
                built = _build_provider("groq", model, api_key, allow_mock=False)
                if built is not None:
                    primaries.append(built)
        elif cfg["api_key"]:
            built = _build_provider("groq", model, cfg["api_key"], allow_mock=False)
            if built is not None:
                primaries.append(built)
    else:
        built = _build_provider(provider, model, cfg["api_key"], allow_mock=True)
        if built is not None:
            primaries.append(built)

    fallback: LLMProvider | None = None
    if cfg.get("fallback_enabled") == "1":
        fb_provider = (cfg.get("fallback_provider") or "").strip().lower()
        fb_model = (cfg.get("fallback_model") or "").strip()
        fb_key = settings.provider_api_key(fb_provider) if fb_provider else ""
        if fb_provider and fb_provider != provider and fb_key:
            fallback = _build_provider(fb_provider, fb_model, fb_key, allow_mock=False)
        elif fb_provider == "mock":
            fallback = MockLLMProvider()

    if not primaries and fallback is None:
        logger.warning("llm_no_providers_available", role=role_key, falling_back="mock")
        instance = MockLLMProvider()
    elif len(primaries) == 1 and fallback is None:
        instance = primaries[0]
    elif not primaries and fallback is not None:
        instance = fallback
    else:
        instance = ResilientLLMProvider(primaries, fallback=fallback, role=role_key)

    _LLM_CACHE[cache_id] = instance
    logger.info(
        "llm_role_bound",
        role=role_key,
        provider=getattr(instance, "name", provider),
        model=getattr(instance, "_model", None)
        or getattr(instance, "_model_name", None)
        or model
        or "mock-1",
        groq_pool=len(settings.groq_api_key_pool()),
        fallback=cfg.get("fallback_provider") if cfg.get("fallback_enabled") == "1" else "off",
    )
    return instance


def clear_llm_cache() -> None:
    _LLM_CACHE.clear()


def llm_role_bindings() -> dict[str, dict[str, Any]]:
    """Resolved role → provider/model (no secrets) for diagnostics."""
    return get_settings().llm_roles_summary()

"""Groq multi-key rotation with optional Google (or other) fallback."""

from __future__ import annotations

from typing import Sequence

from app.core.logging import get_logger
from app.modules.llms.base import LLMProvider, LLMResponse

logger = get_logger("llm_resilient")


class ResilientLLMProvider(LLMProvider):
    """Try primary providers in order (key rotation), then optional fallback."""

    name = "resilient"

    def __init__(
        self,
        primaries: Sequence[LLMProvider],
        *,
        fallback: LLMProvider | None = None,
        role: str = "default",
    ) -> None:
        if not primaries and fallback is None:
            raise ValueError("ResilientLLMProvider needs at least one primary or fallback")
        self._primaries = list(primaries)
        self._fallback = fallback
        self._role = role
        first = self._primaries[0] if self._primaries else fallback
        assert first is not None
        self._model = (
            getattr(first, "_model", None)
            or getattr(first, "_model_name", None)
            or "unknown"
        )
        self.name = first.name if self._primaries else (fallback.name if fallback else "resilient")

    def generate(self, prompt: str, system: str | None = None) -> LLMResponse:
        errors: list[str] = []
        for idx, provider in enumerate(self._primaries):
            try:
                resp = provider.generate(prompt, system=system)
                if idx > 0:
                    logger.info(
                        "llm_key_rotated_success",
                        role=self._role,
                        provider=provider.name,
                        attempt=idx + 1,
                    )
                return resp
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{provider.name}#{idx}: {exc}")
                logger.warning(
                    "llm_primary_failed",
                    role=self._role,
                    provider=provider.name,
                    attempt=idx + 1,
                    error=str(exc),
                )

        if self._fallback is not None:
            logger.warning(
                "llm_falling_back",
                role=self._role,
                fallback=self._fallback.name,
                primary_errors=errors[:5],
            )
            resp = self._fallback.generate(prompt, system=system)
            # Annotate so traces show fallback was used
            return LLMResponse(
                content=resp.content,
                model=resp.model,
                provider=f"{resp.provider}-fallback",
                raw={**(resp.raw or {}), "fallback": True, "primary_errors": errors},
                input_tokens=resp.input_tokens,
                output_tokens=resp.output_tokens,
                total_tokens=resp.total_tokens,
            )

        raise RuntimeError(
            f"All LLM providers failed for role={self._role}: " + " | ".join(errors)
        )

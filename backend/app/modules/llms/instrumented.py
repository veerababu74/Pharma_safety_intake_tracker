"""Wrap any LLM so token usage is attached to the active custom-trace span."""

from __future__ import annotations

from app.modules.llms.base import LLMProvider, LLMResponse
from app.modules.tracing.context import get_current_span


class InstrumentedLLMProvider(LLMProvider):
    """Delegates generate() and records prompt/completion tokens on the current span."""

    def __init__(self, inner: LLMProvider, *, role: str | None = None) -> None:
        self._inner = inner
        self._role = role
        self.name = getattr(inner, "name", "instrumented")

    def generate(self, prompt: str, system: str | None = None) -> LLMResponse:
        resp = self._inner.generate(prompt, system=system)
        span = get_current_span()
        if span is not None:
            # Do not bubble — parents would double-count when the API sums spans.
            span.record_tokens(
                prompt_tokens=resp.input_tokens,
                completion_tokens=resp.output_tokens,
                total_tokens=resp.total_tokens,
                bubble=False,
                llm_role=self._role,
                llm_provider=resp.provider,
                llm_model=resp.model,
            )
        return resp

"""LLM provider abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    raw: dict | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class LLMProvider(ABC):
    name: str

    @abstractmethod
    def generate(self, prompt: str, system: str | None = None) -> LLMResponse:
        raise NotImplementedError

"""Circuit breaker for repeated invalid tool signatures."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class CircuitBreaker:
    limit: int = 2
    _counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def _key(self, tool: str, signature: str) -> str:
        return f"{tool}::{signature}"

    def record_failure(self, tool: str, signature: str) -> bool:
        """Return True if breaker is now open (should halt)."""
        k = self._key(tool, signature)
        self._counts[k] += 1
        return self._counts[k] > self.limit

    def reset(self, tool: str, signature: str) -> None:
        self._counts.pop(self._key(tool, signature), None)

    def snapshot(self) -> dict[str, int]:
        return dict(self._counts)

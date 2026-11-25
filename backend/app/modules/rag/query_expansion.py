"""Query enhancer + multi-query generator for better retrieval coverage."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.core.logging import get_logger
from app.modules.llms.base import LLMProvider
from app.modules.rag.prompts import (
    MULTI_QUERY_SYSTEM,
    QUERY_ENHANCE_SYSTEM,
    build_multi_query_prompt,
    build_query_enhance_prompt,
)

logger = get_logger("query_expansion")


@dataclass
class ExpandedQueries:
    original: str
    enhanced: str
    multi_queries: list[str]

    @property
    def all_queries(self) -> list[str]:
        """Deduped ordered list: original + enhanced + multi (target ~5)."""
        seen: set[str] = set()
        out: list[str] = []
        for q in [self.original, self.enhanced, *self.multi_queries]:
            key = re.sub(r"\s+", " ", q.strip().lower())
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(q.strip())
        return out


def _extract_json_array(raw: str) -> list[str]:
    raw = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw, flags=re.DOTALL)
    payload = fence.group(1) if fence else None
    if payload is None:
        match = re.search(r"\[.*\]", raw, flags=re.DOTALL)
        payload = match.group(0) if match else None
    if not payload:
        raise ValueError("No JSON array in LLM output")
    data = json.loads(payload)
    if not isinstance(data, list):
        raise ValueError("Expected JSON array")
    return [str(x).strip() for x in data if str(x).strip()]


def _heuristic_enhanced(query: str) -> str:
    q = query.strip()
    # Light domain expansion for training SOP/intake retrieval
    extras = []
    lower = q.lower()
    if "lot-" in lower or "lot " in lower:
        extras.append("batch lot quarantine packaging")
    if "seal" in lower or "packaging" in lower or "carton" in lower:
        extras.append("product quality complaint SOP quarantine")
    if "dizzy" in lower or "nausea" in lower or "adverse" in lower:
        extras.append("suspected adverse event intake mandatory fields")
    if not extras:
        extras.append("pharma intake SOP training guidance")
    return f"{q}. Related terms: {', '.join(extras)}"


def _heuristic_multi(query: str, n: int = 3) -> list[str]:
    base = query.strip()
    variants = [
        f"SOP guidance for: {base}",
        f"What intake steps apply to: {base}",
        f"Historical training notes about: {base}",
        f"Mandatory fields and workflow for: {base}",
        f"Quarantine or triage process related to: {base}",
    ]
    return variants[:n]


class QueryExpansionService:
    def __init__(
        self,
        llm: LLMProvider | None = None,
        *,
        enhancer_llm: LLMProvider | None = None,
        rewrite_llm: LLMProvider | None = None,
    ) -> None:
        # `llm` kept for backward compatibility; prefer role-specific LLMs.
        base = llm
        self.enhancer_llm = enhancer_llm or base
        self.rewrite_llm = rewrite_llm or enhancer_llm or base
        if self.enhancer_llm is None or self.rewrite_llm is None:
            raise ValueError("QueryExpansionService requires at least one LLM provider")
        # Alias for older callers/tests
        self.llm = self.enhancer_llm

    def enhance(self, query: str) -> str:
        system = QUERY_ENHANCE_SYSTEM
        prompt = build_query_enhance_prompt(query)
        try:
            resp = self.enhancer_llm.generate(prompt, system=system)
            enhanced = resp.content.strip().splitlines()[0].strip().strip('"')
            if len(enhanced) < 3:
                raise ValueError("Empty enhanced query")
            # Mock LLM often returns long grounded essays — detect and fallback
            if len(enhanced) > 300 or "context excerpt" in enhanced.lower():
                raise ValueError("LLM output not a clean query")
            return enhanced
        except Exception as exc:  # noqa: BLE001
            logger.warning("query_enhance_fallback", error=str(exc))
            return _heuristic_enhanced(query)

    def generate_multi(self, query: str, count: int = 3) -> list[str]:
        system = MULTI_QUERY_SYSTEM
        prompt = build_multi_query_prompt(query, count=count)
        try:
            resp = self.rewrite_llm.generate(prompt, system=system)
            items = _extract_json_array(resp.content)
            cleaned = [q for q in items if len(q) < 300][:count]
            if len(cleaned) < count:
                cleaned.extend(_heuristic_multi(query, count - len(cleaned)))
            return cleaned[:count]
        except Exception as exc:  # noqa: BLE001
            logger.warning("multi_query_fallback", error=str(exc))
            return _heuristic_multi(query, count)

    def expand(
        self,
        query: str,
        *,
        enable_enhancer: bool = True,
        enable_multi: bool = True,
        multi_count: int = 3,
    ) -> ExpandedQueries:
        enhanced = self.enhance(query) if enable_enhancer else query
        multi = self.generate_multi(query, multi_count) if enable_multi else []
        result = ExpandedQueries(original=query, enhanced=enhanced, multi_queries=multi)
        logger.info(
            "queries_expanded",
            total=len(result.all_queries),
            enhanced=enable_enhancer,
            multi=len(multi),
        )
        return result

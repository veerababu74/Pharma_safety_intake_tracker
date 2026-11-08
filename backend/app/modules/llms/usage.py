"""Normalize provider token usage into prompt / completion / total counts."""

from __future__ import annotations

from typing import Any


def estimate_tokens(text: str | None) -> int:
    """Rough local estimate when the provider omits usage (≈4 chars/token)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def tokens_from_usage_dict(usage: Any) -> tuple[int | None, int | None, int | None]:
    if usage is None:
        return None, None, None
    if isinstance(usage, dict):
        prompt = usage.get("prompt_tokens")
        if prompt is None:
            prompt = usage.get("input_tokens")
        completion = usage.get("completion_tokens")
        if completion is None:
            completion = usage.get("output_tokens")
        total = usage.get("total_tokens")
    else:
        prompt = getattr(usage, "prompt_tokens", None)
        if prompt is None:
            prompt = getattr(usage, "input_tokens", None)
        completion = getattr(usage, "completion_tokens", None)
        if completion is None:
            completion = getattr(usage, "output_tokens", None)
        total = getattr(usage, "total_tokens", None)
    try:
        prompt_i = int(prompt) if prompt is not None else None
        completion_i = int(completion) if completion is not None else None
        total_i = int(total) if total is not None else None
    except (TypeError, ValueError):
        return None, None, None
    if total_i is None and prompt_i is not None and completion_i is not None:
        total_i = prompt_i + completion_i
    return prompt_i, completion_i, total_i


def tokens_from_openai_response(resp: Any) -> tuple[int | None, int | None, int | None]:
    usage = getattr(resp, "usage", None)
    if usage is None and isinstance(resp, dict):
        usage = resp.get("usage")
    return tokens_from_usage_dict(usage)


def tokens_from_google_response(resp: Any) -> tuple[int | None, int | None, int | None]:
    meta = getattr(resp, "usage_metadata", None)
    if meta is None:
        return None, None, None
    prompt = getattr(meta, "prompt_token_count", None)
    completion = getattr(meta, "candidates_token_count", None)
    total = getattr(meta, "total_token_count", None)
    try:
        prompt_i = int(prompt) if prompt is not None else None
        completion_i = int(completion) if completion is not None else None
        total_i = int(total) if total is not None else None
    except (TypeError, ValueError):
        return None, None, None
    if total_i is None and prompt_i is not None and completion_i is not None:
        total_i = prompt_i + completion_i
    return prompt_i, completion_i, total_i


def with_estimated_tokens(
    *,
    prompt: str,
    system: str | None,
    content: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    total_tokens: int | None,
) -> tuple[int, int, int]:
    """Fill missing sides with a local estimate so traces always show numbers."""
    in_tok = prompt_tokens if prompt_tokens is not None else estimate_tokens(
        f"{system or ''}\n{prompt}"
    )
    out_tok = completion_tokens if completion_tokens is not None else estimate_tokens(content)
    total = total_tokens if total_tokens is not None else in_tok + out_tok
    return int(in_tok), int(out_tok), int(total)

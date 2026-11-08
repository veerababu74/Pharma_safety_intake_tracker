"""LLM helpers for social replies and user-facing response drafting."""

from __future__ import annotations

import json
from typing import Any

from app.core.container import get_container
from app.core.logging import get_logger
from app.modules.agents.prompts import (
    RESPONSE_DRAFT_SYSTEM,
    SOCIAL_SYSTEM,
    build_response_draft_prompt,
    build_social_prompt,
    social_fallback,
)

logger = get_logger("agent_response_llm")

_SAFETY = RESPONSE_DRAFT_SYSTEM


def _history_block(history: list[dict[str, str]] | None, limit: int = 6) -> str:
    if not history:
        return "(no prior turns)"
    lines = [f"{h.get('role', 'user')}: {h.get('content', '')}" for h in history[-limit:]]
    return "\n".join(lines)


def _clean_llm_text(raw: str, fallback: str) -> str:
    text = (raw or "").strip()
    if not text:
        return fallback
    # Mock / noisy models sometimes dump long context essays
    lower = text.lower()
    if (
        "context excerpt considered" in lower
        or "based only on the provided training context" in lower
        or "no context" in lower
        or len(text) > 1600
    ):
        return fallback
    return text


def _pretty_lookup_fallback(facts: str) -> str:
    """Build a clean markdown card from get_report JSON facts."""
    try:
        data = json.loads(facts) if facts.strip().startswith("{") else None
    except Exception:
        data = None
    report = (data or {}).get("report") if isinstance(data, dict) else None
    if not isinstance(report, dict):
        return facts
    ref = report.get("reference_id", "—")
    status = report.get("status", "—")
    pending = report.get("pending_close")
    lines = [
        f"### {ref}",
        "",
        f"- **Status:** {status}"
        + (" · pending close (waiting for HITL)" if pending else ""),
        f"- **Type:** {report.get('report_type', '—')}",
        f"- **Product:** {report.get('product_name', '—')}",
        f"- **Lot:** {report.get('batch_lot_number', '—')}",
        f"- **Date received:** {report.get('date_received', '—')}",
        f"- **Reporter:** {report.get('reporter_type', '—')}",
        f"- **Created by:** {report.get('created_by', '—')}",
    ]
    desc = (report.get("description") or "").strip()
    if desc:
        lines.extend(["", "**Description**", "", desc])
    return "\n".join(lines)


def draft_user_response(
    *,
    kind: str,
    user_message: str,
    facts: str,
    fallback: str,
    actor: str | None = None,
    role: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> str:
    """Turn structured tool/route facts into a natural end-user reply."""
    # For single-report lookup, prefer a deterministic pretty card so status cannot drift
    if kind == "lookup_one":
        pretty = _pretty_lookup_fallback(facts)
        # Still allow a light LLM polish, but if it changes status/REF, keep pretty
        polished = None
        try:
            llm = get_container().llm_for("response")
            prompt = (
                f"User asked: {user_message}\n\n"
                f"Exact report facts (DO NOT change status or IDs):\n{facts}\n\n"
                "Rewrite as a short friendly markdown reply for the UI.\n"
                "Rules:\n"
                "- Keep the exact status string from facts\n"
                "- Keep the exact reference_id\n"
                "- Use markdown: ## heading, bullets, **bold** labels\n"
                "- No JSON dumps\n"
                "- No inventing fields\n"
            )
            polished = _clean_llm_text(
                llm.generate(prompt, system=_SAFETY).content,
                pretty,
            )
            # Guard: status string from facts must appear in polished text
            try:
                report = json.loads(facts).get("report") or {}
                st = str(report.get("status") or "")
                ref = str(report.get("reference_id") or "")
                if st and st not in polished:
                    return pretty
                if ref and ref not in polished:
                    return pretty
            except Exception:
                return pretty
            return polished
        except Exception:
            return pretty

    if kind == "rag":
        # Prefer the grounded rag_answer; LLM may polish style only
        rag_answer = ""
        sources: list[Any] = []
        try:
            payload = json.loads(facts)
            rag_answer = str(payload.get("rag_answer") or "").strip()
            sources = payload.get("sources") or []
        except Exception:
            rag_answer = ""
            sources = []

        def _ungrounded(text: str) -> bool:
            lower = (text or "").lower()
            return any(
                p in lower
                for p in (
                    "insufficient",
                    "does not include",
                    "don't have enough",
                    "do not have enough",
                    "consult the internal",
                    "consult an internal",
                    "reach out to the quality",
                    "available information does not",
                    "i'm sorry, but the available",
                    "i am sorry, but the available",
                )
            )

        grounded_from_sources = ""
        if sources:
            bits = []
            for s in sources[:4]:
                if not isinstance(s, dict):
                    continue
                preview = str(s.get("text") or s.get("text_preview") or "").strip()
                doc = s.get("doc_id") or s.get("chunk_id") or "source"
                if preview:
                    bits.append(f"- ({doc}) {preview[:320]}")
            if bits:
                grounded_from_sources = (
                    "Grounded SOP excerpts:\n" + "\n".join(bits)
                )

        if not rag_answer or _ungrounded(rag_answer):
            if not sources:
                return (
                    "I could not find enough grounded SOP evidence for that question "
                    "in the indexed knowledge base.\n\n"
                    "- Try asking about packaging quarantine / LOT-88392 after documents are indexed\n"
                    "- Or rephrase using words from the uploaded SOPs\n"
                    "- Admin can confirm docs under **Admin Docs**"
                )
            # Retrieval hit but generation/polish was vague — answer from chunks
            base = grounded_from_sources or fallback
        else:
            base = rag_answer or fallback

        prompt = (
            f"Task type: rag\n"
            f"User: {user_message}\n\n"
            f"Grounded SOP facts (source of truth — do not contradict):\n{base}\n\n"
            f"Sources available: {len(sources)}\n\n"
            "Write a polished markdown reply for chat:\n"
            "- Short heading + numbered or bulleted action steps\n"
            "- Keep concrete facts (quarantine timing, mailboxes, LOT numbers)\n"
            "- Do not invent procedures\n"
            "- Do NOT say 'consult an internal SOP' or 'reach out to QA' when steps are already present\n"
        )
        try:
            llm = get_container().llm_for("response")
            text = _clean_llm_text(llm.generate(prompt, system=_SAFETY).content, base)
            if _ungrounded(text) and grounded_from_sources:
                return (
                    "### Packaging complaint guidance\n\n"
                    f"{grounded_from_sources}\n\n"
                    "Follow the quarantine / notify steps in the excerpts above "
                    "(training SOP — fictional)."
                )
            return text
        except Exception:
            return base

    # Never let the response LLM invent a successful status change
    if kind in {"status_needs_args", "status_close_error", "status_validation_error"}:
        return fallback

    if kind == "status_updated":
        pretty = _pretty_lookup_fallback(facts) if facts.strip().startswith("{") else fallback
        try:
            report = json.loads(facts).get("report") or {}
            st = str(report.get("status") or "")
            if st and st not in {"New", "In Review", "Closed"}:
                return pretty or fallback
            polished = None
            llm = get_container().llm_for("response")
            prompt = (
                f"User asked: {user_message}\n\n"
                f"Exact updated report facts (DO NOT invent other statuses):\n{facts}\n\n"
                "Confirm the status change briefly in markdown. "
                "Only statuses New / In Review / Closed exist.\n"
            )
            polished = _clean_llm_text(llm.generate(prompt, system=_SAFETY).content, pretty)
            if st and st not in polished:
                return pretty
            if any(bad in polished.lower() for bad in ("review completed", "approved → closed")):
                # Keep grounded card if model invents fake workflow labels
                if "review completed" in polished.lower() and st != "Closed":
                    return pretty
            return polished
        except Exception:
            return pretty or fallback

    prompt = build_response_draft_prompt(
        kind=kind,
        user_message=user_message,
        actor=actor,
        role=role,
        history_block=_history_block(history),
        facts=facts,
    )
    tracer = get_container().tracer
    try:
        with tracer.span(
            "agent_response_draft",
            kind="generation",
            actor=actor,
            role=role,
            input_preview=prompt[:1500],
            metadata={"flow": "agent", "step": "response_draft", "kind": kind, "llm_role": "response"},
        ) as span:
            llm = get_container().llm_for("response")
            raw = llm.generate(prompt, system=RESPONSE_DRAFT_SYSTEM).content
            text = _clean_llm_text(raw, fallback)
            span.set_output(text)
            span.update(kind=kind, used_fallback=text == fallback, llm_provider=getattr(llm, "name", None))
            return text
    except Exception as exc:  # noqa: BLE001
        logger.warning("draft_user_response_failed", error=str(exc), kind=kind)
        return fallback


def social_agent_reply(
    *,
    user_message: str,
    actor: str | None = None,
    role: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> str:
    """Dedicated social/direct agent for greetings, thanks, help, chit-chat."""
    fallback = social_fallback(actor=actor)
    prompt = build_social_prompt(
        user_message=user_message,
        actor=actor,
        role=role,
        history_block=_history_block(history),
    )
    try:
        llm = get_container().llm_for("social")
        raw = llm.generate(prompt, system=SOCIAL_SYSTEM).content
        return _clean_llm_text(raw, fallback)
    except Exception as exc:  # noqa: BLE001
        logger.warning("social_agent_reply_failed", error=str(exc))
        return fallback


def facts_json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)

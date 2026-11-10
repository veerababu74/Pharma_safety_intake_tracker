"""LangGraph router agent with tools, chat-aware state, and HITL interrupt."""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Literal, TypedDict

from langgraph.config import get_config
from langgraph.graph import END, StateGraph
from langgraph.types import Command, interrupt
from pydantic import ValidationError

from app.auth.roles import has_permission
from app.core.config import get_settings
from app.core.container import get_container
from app.core.logging import get_logger
from app.modules.agents.checkpointer import get_checkpointer
from app.modules.agents.circuit_breaker import CircuitBreaker
from app.modules.agents.prompts import (
    ROUTER_EXAMPLES,
    ROUTER_SYSTEM,
    build_router_prompt,
)
from app.modules.agents.response_llm import draft_user_response, facts_json, social_agent_reply
from app.modules.agents.tool_backend import get_agent_tool_map, invoke_approve_close
from app.modules.agents.tools import (
    LOT_RE,
    SubmitIntakeInput,
    UpdateStatusInput,
)
from app.services.chat_service import ChatHistoryService
from app.services.report_service import ReportService

logger = get_logger("langgraph_agent")

Intent = Literal["direct", "rag", "intake", "status", "lookup", "unknown"]

_UNICODE_DASHES = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
    }
)
_LOT_TOKEN_RE = re.compile(r"\bLOT-\d+\b", re.IGNORECASE)
_REPORTER_RE = re.compile(
    r"reporter(?:\s+type)?\s*[:=]?\s*"
    r"(Consumer|Healthcare Professional|Pharmacist|Other)\b",
    re.IGNORECASE,
)
_DATE_RECEIVED_RE = re.compile(
    r"(?:date\s+received|received(?:\s+date)?|date)\s*[:=]?\s*"
    r"(\d{4}-\d{2}-\d{2}|today)\b",
    re.IGNORECASE,
)
_PRODUCT_BEFORE_LOT_RE = re.compile(
    r"\bfor\s+(.+?)\s+(?=LOT-\d+)",
    re.IGNORECASE,
)
_PRODUCT_NAMED_RE = re.compile(
    r"product(?:\s+name)?\s*[:=]\s*(.+?)(?=\s+LOT-\d+|\s*[,.]|$)",
    re.IGNORECASE,
)
_DESC_AFTER_LOT_RE = re.compile(
    r"LOT-\d+\s*[,:\-]?\s*(.+?)(?="
    r"\.\s*Reporter|\.\s*Date\s+received|Reporter(?:\s+type)?|"
    r"Date\s+received|Event\s+description|Onset|$)",
    re.IGNORECASE | re.DOTALL,
)
_EVENT_DESC_RE = re.compile(
    r"event\s+description\s*[:=]?\s*(.+?)(?=\.\s*Onset|\.\s*Reporter|Onset|Reporter|Date\s+received|$)",
    re.IGNORECASE | re.DOTALL,
)
_ONSET_RE = re.compile(
    r"(?:event\s+)?onset(?:\s+date)?\s*[:=]?\s*(\d{4}-\d{2}-\d{2})\b",
    re.IGNORECASE,
)


def _normalize_message(text: str) -> str:
    """ASCII-normalize unicode dashes so LOT‑1111 still tokenizes."""
    return (text or "").translate(_UNICODE_DASHES)


def _soft_message(message: str) -> str:
    text = _normalize_message(message).lower().strip()
    soft = re.sub(r"[^\w\s\-]", " ", text)
    return re.sub(r"\s+", " ", soft).strip()


def _is_intake_create_request(soft: str) -> bool:
    return any(
        k in soft
        for k in (
            "create",
            "submit",
            "intake",
            "new report",
            "file a",
            "file pqc",
            "log a",
            "log pqc",
            "open a suspected",
            "open an adverse",
            "open a pqc",
            "i need to log",
        )
    )


def _is_lot_lookup_request(soft: str) -> bool:
    """Read-only lot detail / find-by-lot questions (not SOP guidance, not create)."""
    if _is_intake_create_request(soft):
        return False
    if any(
        k in soft
        for k in (
            "sop",
            "quarantine",
            "what should",
            "guidance",
            "how do",
            "policy",
            "historical",
            "packaging complaint",
        )
    ):
        return False
    if re.fullmatch(r"lot-\d+", soft):
        return True
    if _LOT_TOKEN_RE.search(soft) and any(
        k in soft
        for k in (
            "details",
            "give me",
            "show",
            "find",
            "lookup",
            "look up",
            "status",
            "reports for",
            "about",
            "for lot",
        )
    ):
        return True
    return False


def _parse_intake_from_message(message: str) -> dict[str, Any] | None:
    """Best-effort NL field extraction for prose intake creates."""
    text = _normalize_message(message).strip()
    if not text:
        return None
    soft = re.sub(r"\s+", " ", text)
    lower = soft.lower()
    args: dict[str, Any] = {}

    if any(
        k in lower
        for k in (
            "product quality complaint",
            "product quality",
            "packaging complaint",
            "quality complaint",
            " pqc ",
            "pqc for",
            "file a pqc",
            "log a pqc",
            "create a pqc",
            "submit a pqc",
        )
    ) or lower.startswith("pqc ") or "create a pqc" in lower:
        args["report_type"] = "Product Quality Complaint"
    elif any(
        k in lower
        for k in (
            "suspected adverse event",
            "adverse event",
            "suspected ae",
            "open an adverse",
            "open a suspected",
        )
    ):
        args["report_type"] = "Suspected Adverse Event"

    lot_m = _LOT_TOKEN_RE.search(soft)
    if lot_m:
        args["batch_lot_number"] = lot_m.group(0).upper()

    prod_m = _PRODUCT_BEFORE_LOT_RE.search(soft) or _PRODUCT_NAMED_RE.search(soft)
    if prod_m:
        product = re.sub(r"\s+", " ", prod_m.group(1)).strip(" .,;:-")
        # Drop leading report-type phrasing stuck in the capture
        product = re.sub(
            r"^(?:a\s+)?(?:product\s+quality\s+complaint|packaging\s+complaint|"
            r"quality\s+complaint|pqc|suspected\s+adverse\s+event|adverse\s+event)\s+",
            "",
            product,
            flags=re.IGNORECASE,
        ).strip(" .,;:-")
        if product:
            args["product_name"] = product

    rep_m = _REPORTER_RE.search(soft)
    if rep_m:
        canon = {
            "consumer": "Consumer",
            "healthcare professional": "Healthcare Professional",
            "pharmacist": "Pharmacist",
            "other": "Other",
        }
        args["reporter_type"] = canon[rep_m.group(1).lower()]

    date_m = _DATE_RECEIVED_RE.search(soft)
    if date_m:
        raw_date = date_m.group(1).lower()
        args["date_received"] = date.today().isoformat() if raw_date == "today" else date_m.group(1)

    if args.get("report_type") == "Suspected Adverse Event":
        ed_m = _EVENT_DESC_RE.search(soft)
        if ed_m:
            args["event_description"] = re.sub(r"\s+", " ", ed_m.group(1)).strip(" .,;:-")
        onset_m = _ONSET_RE.search(soft)
        if onset_m:
            args["event_onset_date"] = onset_m.group(1)

    desc_m = _DESC_AFTER_LOT_RE.search(soft)
    if desc_m:
        desc = re.sub(r"\s+", " ", desc_m.group(1)).strip(" .,;:-")
        # Avoid treating reporter/date fragments as description
        if desc and not re.fullmatch(r"(?:reporter|date|consumer|pharmacist|other).*", desc, re.I):
            args["description"] = desc
    if not args.get("description") and args.get("event_description"):
        args["description"] = args["event_description"]

    return args or None


class AgentState(TypedDict, total=False):
    message: str
    actor: str
    role: str
    session_id: str
    thread_id: str
    intent: str
    route_meta: dict[str, Any]
    tool_args: dict[str, Any]
    response: str
    details: dict[str, Any]
    halted: bool
    needs_hitl: bool
    hitl_request_id: str
    chat_history: list[dict[str, str]]


_breaker = CircuitBreaker(limit=2)
_reports = ReportService()
_chat = ChatHistoryService()


def _hitl_session_thread(state: AgentState) -> tuple[str, str]:
    """Prefer state channels; fall back to LangGraph configurable thread_id."""
    session_id = str(state.get("session_id") or "").strip()
    thread_id = str(state.get("thread_id") or "").strip()
    if not thread_id:
        try:
            cfg = get_config() or {}
            thread_id = str((cfg.get("configurable") or {}).get("thread_id") or "").strip()
        except Exception:  # noqa: BLE001
            thread_id = ""
    return session_id, thread_id


def _thread_has_pending_interrupt(thread_id: str) -> bool:
    if not (thread_id or "").strip():
        return False
    try:
        tup = get_checkpointer().get_tuple({"configurable": {"thread_id": thread_id}})
        if not tup:
            return False
        return bool(getattr(tup, "interrupts", None) or ())
    except Exception:  # noqa: BLE001
        return False


def _tools() -> dict:
    """Resolve tool map from AGENT_TOOL_BACKEND (local tools.py or FastMCP)."""
    return get_agent_tool_map()


def _is_status_change_request(soft: str) -> bool:
    """True only when the user wants to *change* workflow status, not ask about it."""
    change_markers = [
        "move to",
        "move ref",
        "change status",
        "set status",
        "update status",
        "start review",
        "start the review",
        "begin review",
        "begin the review",
        "complete the review",
        "complete review",
        "review is completed",
        "review completed",
        "review complete",
        "mark this one review",
        "mark review",
        "finish the review",
        "finish review",
        "put in review",
        "send to review",
        "move to review",
        "move to approver",
        "send to approver",
        "send for approval",
        "submit to approver",
        "hand off to approver",
        "handoff to approver",
        "ready for approver",
        "approve close",
        "request close",
        "make request close",
        "please close",
        "close ref-",
        "close this",
        "close it",
        "close case",
        "close the ticket",
        "close the case",
        "mark as closed",
        "mark closed",
        "to in review",
        "to closed",
    ]
    return any(k in soft for k in change_markers) or bool(
        re.search(r"\bclose\s+ref-\d{4}-\d{4}\b", soft)
    )


_ALLOWED_STATUSES = frozenset({"New", "In Review", "Closed"})


def _canonical_status(raw: str | None) -> str | None:
    """Map free-text / invented labels onto the only real workflow statuses."""
    if not raw:
        return None
    s = re.sub(r"\s+", " ", str(raw).strip().lower())
    if s in {
        "closed",
        "close",
        "closing",
        "review completed",
        "review complete",
        "review is completed",
        "review is complete",
        "complete review",
        "complete the review",
        "finish review",
        "finish the review",
        "pending approval",
        "approver",
        "awaiting approver",
    }:
        # Completing review / sending to approver = request Closed (HITL)
        return "Closed"
    if s in {"new"}:
        return "New"
    if s in {
        "in review",
        "review",
        "under review",
        "start review",
        "start the review",
    }:
        return "In Review"
    if raw in _ALLOWED_STATUSES:
        return raw
    return None


def _infer_new_status(soft: str) -> str | None:
    """Map natural-language change phrases to workflow status. Never invent extra statuses."""
    # Close / send-to-approver first (reviewer finished triage → HITL)
    if any(
        k in soft
        for k in (
            "approve close",
            "request close",
            "make request close",
            "please close",
            "close this",
            "close it",
            "close case",
            "close the ticket",
            "close the case",
            "mark as closed",
            "mark closed",
            "to closed",
            "close ref-",
            "move to approver",
            "send to approver",
            "send for approval",
            "submit to approver",
            "hand off to approver",
            "handoff to approver",
            "ready for approver",
            "complete the review",
            "complete review",
            "review is completed",
            "review completed",
            "review complete",
            "finish the review",
            "finish review",
        )
    ) or bool(re.search(r"\bclose\s+ref-\d{4}-\d{4}\b", soft)):
        return "Closed"
    if any(
        k in soft
        for k in (
            "in review",
            "start review",
            "start the review",
            "begin review",
            "begin the review",
            "mark this one review",
            "mark review",
            "put in review",
            "send to review",
            "move to review",
            "to in review",
        )
    ):
        return "In Review"
    if re.search(r"\bclose\b", soft):
        return "Closed"
    return None


def _normalize_status_soft(message: str) -> str:
    """Soft-normalize status phrases (common typos + unicode dashes)."""
    soft = _soft_message(message)
    return (
        soft.replace("reviewo", "review")
        .replace("everthing", "everything")
        .replace("complet the", "complete the")
    )


def _extract_reviewer_notes(msg: str) -> str | None:
    """Pull triage notes from explicit notes: clauses or trailing 'with details…' text."""
    notes_m = re.search(
        r"(?:reviewer[_\s-]?notes|notes|triage)\s*[:=]\s*(.+)$",
        msg,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if notes_m:
        return notes_m.group(1).strip().strip("`\"'")

    detail_m = re.search(
        r"(?:complete(?:d)?\s+the\s+review\w*|finish(?:ed)?\s+(?:the\s+)?review\w*|"
        r"move\s+to\s+approver|send\s+to\s+approver|request\s+close|close\s+it|"
        r"ready\s+for\s+approver)"
        r"[\s\S]*?(?:with\s+(?:the\s+)?details?\s+(?:of\s+)?|—\s*|–\s*|-\s+)(.+)$",
        msg,
        flags=re.IGNORECASE,
    )
    if detail_m:
        note = detail_m.group(1).strip().strip("`\"'")
        if note and len(note) >= 3:
            return note
    return None


def _is_status_inquiry(soft: str) -> bool:
    """True when the user is asking what the status/details are (read-only)."""
    inquiry = [
        "status of",
        "current status",
        "what is the status",
        "what's the status",
        "whats the status",
        "give me the status",
        "tell me the status",
        "check status",
        "show status",
        "get status",
        "status for",
        "status please",
        "ticket status",
        "ticket statues",  # common typo
        "give me this ticket",
        "is it closed",
        "is it in review",
        "actually its",
        "actually it's",
        "actually it is",
        "wrong status",
        "under closed",
        "already closed",
    ]
    if any(k in soft for k in inquiry):
        return True
    # "REF-... status/statues" without change verbs
    if ("status" in soft or "statues" in soft) and not _is_status_change_request(soft):
        return True
    return False


def _rule_route(message: str) -> Intent:
    soft = _soft_message(message)

    social_exact = {
        "hi",
        "hello",
        "hey",
        "thanks",
        "thank you",
        "help",
        "bye",
        "goodbye",
        "good morning",
        "good afternoon",
        "good evening",
    }
    if (
        soft in social_exact
        or soft.startswith(("hello", "hi ", "hey ", "thanks", "thank you", "good morning", "good afternoon"))
        or any(
            p in soft
            for p in [
                "who are you",
                "what can you",
                "how can you help",
                "what do you do",
                "nice to meet",
            ]
        )
    ):
        return "direct"
    # Read-only status / details questions → lookup (never update_status)
    if _is_status_inquiry(soft):
        return "lookup"
    if _is_lot_lookup_request(soft):
        return "lookup"
    if any(
        k in soft
        for k in [
            "list reports",
            "show reports",
            "list all",
            "list cases",
            "show cases",
            "get report",
            "find ref-",
            "lookup ref",
            "show me ref-",
            "recent reports",
            "details of ref",
            "detail of ref",
            "give me ref",
            "in review cases",
            "closed cases",
            "new cases",
        ]
    ) or (re.search(r"ref-\d{4}-\d{4}", soft) and not _is_status_change_request(soft)):
        return "lookup"
    if _is_status_change_request(soft) or any(
        k in soft for k in ["approve close", "start review", "move to", "change status"]
    ):
        return "status"
    if _is_intake_create_request(soft):
        return "intake"
    # "complaint" alone often means SOP guidance (packaging complaint), not create
    if any(
        k in soft
        for k in [
            "sop",
            "quarantine",
            "lot-",
            "what should",
            "guidance",
            "policy",
            "how do",
            "mandatory",
            "historical",
            "packaging complaint",
            "what does the",
        ]
    ):
        return "rag"
    if "complaint" in soft or "adverse" in soft:
        # Ambiguous — prefer RAG unless clearly creating
        if any(k in soft for k in ["create", "submit", "file", "log", "new "]):
            return "intake"
        return "rag"
    return "rag"


def _extract_route_label(raw: str) -> Intent | None:
    text = (raw or "").strip().lower()
    # Reject long/noisy generations (common with mock LLM)
    if len(text) > 40 or "context excerpt" in text or "based only on the provided" in text:
        return None
    first_line = text.splitlines()[0].strip()
    first = first_line.split()[0].strip(".,:`\"'") if first_line.split() else ""
    if first in {"direct", "rag", "intake", "status", "lookup"}:
        return first  # type: ignore[return-value]
    for key in ("direct", "rag", "intake", "status", "lookup"):
        if first_line == key or first_line.endswith(f"label: {key}") or first_line.endswith(f"=> {key}"):
            return key  # type: ignore[return-value]
    return None


def _llm_route(message: str, history: list[dict[str, str]]) -> tuple[Intent | None, dict[str, Any]]:
    """Few-shot LLM router; falls back to None on failure/mock noise."""
    meta: dict[str, Any] = {"router_source": "llm"}
    try:
        from app.core.config import get_settings

        cfg = get_settings().resolve_llm_role("router")
        meta.update({"llm_provider": cfg["provider"], "llm_model": cfg["model"], "llm_role": "router"})
        llm = get_container().llm_for("router")
        hist = "\n".join(f"{h.get('role')}: {h.get('content')}" for h in history[-6:])
        prompt = build_router_prompt(
            message=message,
            history_block=hist,
            examples=ROUTER_EXAMPLES,
        )
        resp = llm.generate(prompt, system=ROUTER_SYSTEM)
        meta["llm_provider"] = resp.provider
        meta["llm_model"] = resp.model
        meta["raw_label"] = (resp.content or "")[:80]
        label = _extract_route_label(resp.content)
        if label:
            meta["intent"] = label
            return label, meta
        meta["router_source"] = "llm_rejected"
    except Exception as exc:  # noqa: BLE001
        logger.warning("llm_router_failed", error=str(exc))
        meta["error"] = str(exc)
        meta["router_source"] = "llm_error"
    return None, meta


def router_node(state: AgentState) -> AgentState:
    tracer = get_container().tracer
    message = state.get("message", "")
    soft = _soft_message(message)
    with tracer.span(
        "agent_router",
        kind="generation",
        actor=state.get("actor"),
        role=state.get("role"),
        input_preview=message,
        metadata={
            "flow": "agent",
            "step": "router",
            "session_id": state.get("session_id"),
            "thread_id": state.get("thread_id"),
        },
    ) as span:
        # Deterministic overrides — LLM must not turn status questions into updates
        # or invent status changes / mis-route create+complaint to RAG.
        if _is_status_inquiry(soft) and not _is_status_change_request(soft):
            intent = "lookup"
            route_meta = {"router_source": "rules_safe", "intent": intent}
        elif _is_status_change_request(soft):
            intent = "status"
            route_meta = {"router_source": "rules_safe", "intent": intent}
        elif _is_intake_create_request(soft):
            intent = "intake"
            route_meta = {"router_source": "rules_safe", "intent": intent}
        elif _is_lot_lookup_request(soft):
            intent = "lookup"
            route_meta = {"router_source": "rules_safe", "intent": intent}
        elif (
            re.search(r"lot-\d{5}", soft)
            and any(k in soft for k in ("what should", "packaging", "quarantine", "sop", "how do", "complaint"))
            and not _is_intake_create_request(soft)
        ):
            intent = "rag"
            route_meta = {"router_source": "rules_safe", "intent": intent}
        else:
            llm_intent, route_meta = _llm_route(message, state.get("chat_history") or [])
            if llm_intent:
                # Never trust LLM "status" unless the message clearly asks to change status
                if llm_intent == "status" and not _is_status_change_request(soft):
                    intent = _rule_route(message)
                    if intent == "status":
                        intent = "lookup"
                    route_meta = {**route_meta, "router_source": "rules_override_llm_status", "intent": intent}
                elif llm_intent == "rag" and _is_intake_create_request(soft):
                    intent = "intake"
                    route_meta = {**route_meta, "router_source": "rules_override_llm_intake", "intent": intent}
                elif llm_intent == "rag" and _is_lot_lookup_request(soft):
                    intent = "lookup"
                    route_meta = {**route_meta, "router_source": "rules_override_llm_lookup", "intent": intent}
                else:
                    intent = llm_intent
            else:
                intent = _rule_route(message)
                route_meta = {**route_meta, "router_source": "rules", "intent": intent}
        span.set_output({"intent": intent, "router_source": route_meta.get("router_source")})
        span.update(**route_meta)
    logger.info("routed", intent=intent, actor=state.get("actor"), source=route_meta.get("router_source"))
    return {**state, "intent": intent, "route_meta": route_meta}


def direct_node(state: AgentState) -> AgentState:
    tracer = get_container().tracer
    with tracer.span(
        "agent_social",
        kind="generation",
        actor=state.get("actor"),
        role=state.get("role"),
        input_preview=state.get("message", ""),
        metadata={"flow": "agent", "step": "social", "tool": "social_agent"},
    ) as span:
        reply = social_agent_reply(
            user_message=state.get("message", ""),
            actor=state.get("actor"),
            role=state.get("role"),
            history=state.get("chat_history"),
        )
        span.set_output(reply)
    return {**state, "response": reply, "details": {"route": "direct", "social_agent": True}}


def rag_node(state: AgentState) -> AgentState:
    tracer = get_container().tracer
    with tracer.span(
        "agent_tool_hybrid_rag_query",
        kind="tool",
        actor=state.get("actor"),
        role=state.get("role"),
        input_preview=state.get("message", ""),
        metadata={"flow": "agent", "step": "tool", "tool": "hybrid_rag_query"},
    ) as span:
        tool = _tools()["hybrid_rag_query"]
        raw = tool.invoke(
            {
                "question": state["message"],
                "actor": state.get("actor", "system"),
                "role": state.get("role", "operator"),
            }
        )
        data = json.loads(raw) if isinstance(raw, str) else raw
        answer = data.get("answer") or "Insufficient grounded context."
        span.set_output(
            {
                "answer_preview": (answer or "")[:800],
                "source_ids": [s.get("chunk_id") for s in (data.get("sources") or [])[:8]],
                "diagnostics": data.get("diagnostics"),
            }
        )
        span.update(
            tool="hybrid_rag_query",
            source_count=len(data.get("sources") or []),
            llm_provider=(data.get("diagnostics") or {}).get("llm_provider"),
            llm_model=(data.get("diagnostics") or {}).get("llm_model"),
        )
    response = draft_user_response(
        kind="rag",
        user_message=state.get("message", ""),
        facts=facts_json(
            {
                "rag_answer": answer,
                "sources": data.get("sources", [])[:5],
                "query_expansion": data.get("query_expansion"),
            }
        ),
        fallback=answer,
        actor=state.get("actor"),
        role=state.get("role"),
        history=state.get("chat_history"),
    )
    return {
        **state,
        "response": response,
        "details": {"route": "rag", "rag": data},
    }


def _extract_json_blob(text: str) -> dict[str, Any] | None:
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _intake_missing_fields(args: dict[str, Any]) -> list[str]:
    required = [
        "report_type",
        "product_name",
        "batch_lot_number",
        "date_received",
        "reporter_type",
        "description",
    ]
    missing = [f for f in required if not str(args.get(f) or "").strip()]
    if args.get("report_type") == "Suspected Adverse Event":
        if not str(args.get("event_description") or "").strip():
            missing.append("event_description")
        if not str(args.get("event_onset_date") or "").strip():
            missing.append("event_onset_date")
    return missing


def _format_intake_validation_error(errors: list[Any], args: dict[str, Any]) -> str:
    lot = str(args.get("batch_lot_number") or "").strip()
    msgs: list[str] = []
    for err in errors:
        if not isinstance(err, dict):
            msgs.append(str(err))
            continue
        loc = ".".join(str(x) for x in (err.get("loc") or ()))
        msg = str(err.get("msg") or "invalid")
        if "batch_lot_number" in loc or "LOT-#####" in msg:
            msgs.append(
                f"`{lot or 'lot'}` is invalid — batch_lot_number must match "
                "**LOT-#####** (exactly 5 digits, e.g. LOT-01111)."
            )
        else:
            msgs.append(f"{loc or 'field'}: {msg}")
    body = "\n".join(f"- {m}" for m in msgs) if msgs else "- Validation failed"
    return (
        "### Intake not created\n\n"
        "No report was saved. Fix the fields below and resubmit:\n\n"
        f"{body}"
    )


def intake_node(state: AgentState) -> AgentState:
    role = state.get("role") or "operator"
    if not has_permission(role, "intake:create"):
        fallback = (
            f"Your role (`{role}`) cannot create intake reports. "
            "Ask an operator, reviewer, or admin."
        )
        return {
            **state,
            "response": fallback,
            "details": {"route": "intake", "denied": True},
        }

    args = dict(state.get("tool_args") or {})
    if not args:
        # Prefer JSON blob when present; otherwise parse prose fields from the message.
        parsed = _extract_json_blob(state.get("message", ""))
        if parsed:
            args = parsed
        else:
            args = _parse_intake_from_message(state.get("message", "")) or {}

    missing = _intake_missing_fields(args) if args else [
        "report_type",
        "product_name",
        "batch_lot_number",
        "date_received",
        "reporter_type",
        "description",
    ]
    if not args or missing:
        parsed_bits = {
            k: v
            for k, v in args.items()
            if k not in {"actor", "role"} and str(v or "").strip()
        }
        fallback = (
            "### Intake needs more details\n\n"
            "No report was created yet. Needed fields: report_type, product_name, "
            "batch_lot_number (**LOT-#####** with exactly 5 digits), date_received "
            "(YYYY-MM-DD or today), reporter_type, description "
            "(+ event_description / event_onset_date for AE).\n\n"
            f"Missing: {', '.join(missing) if missing else 'all required fields'}\n"
        )
        if parsed_bits:
            fallback += f"\nParsed so far: `{json.dumps(parsed_bits, default=str)}`"
        return {
            **state,
            "response": draft_user_response(
                kind="intake_needs_args",
                user_message=state.get("message", ""),
                facts=fallback,
                fallback=fallback,
                actor=state.get("actor"),
                role=state.get("role"),
                history=state.get("chat_history"),
            ),
            "details": {"route": "intake", "needs_args": True, "parsed": parsed_bits, "missing": missing},
        }

    args["actor"] = state.get("actor", "operator")
    args["role"] = state.get("role", "operator")
    signature = str(sorted((k, str(v)) for k, v in args.items() if k not in {"actor", "role"}))
    try:
        validated = SubmitIntakeInput(**args)
    except ValidationError as exc:
        if _breaker.record_failure("submit_intake_report", signature):
            fallback = "Circuit breaker open: repeated invalid submit_intake_report arguments."
            return {
                **state,
                "response": draft_user_response(
                    kind="intake_circuit_breaker",
                    user_message=state.get("message", ""),
                    facts=facts_json({"errors": exc.errors(), "halted": True}),
                    fallback=fallback,
                    actor=state.get("actor"),
                    role=state.get("role"),
                    history=state.get("chat_history"),
                ),
                "halted": True,
                "details": {"route": "intake", "errors": exc.errors()},
            }
        fallback = _format_intake_validation_error(exc.errors(), args)
        return {
            **state,
            "response": draft_user_response(
                kind="intake_validation_error",
                user_message=state.get("message", ""),
                facts=facts_json({"errors": exc.errors(), "parsed": args}),
                fallback=fallback,
                actor=state.get("actor"),
                role=state.get("role"),
                history=state.get("chat_history"),
            ),
            "halted": False,
            "details": {"route": "intake", "errors": exc.errors()},
        }

    _breaker.reset("submit_intake_report", signature)
    tracer = get_container().tracer
    with tracer.span(
        "agent_tool_submit_intake_report",
        kind="tool",
        actor=state.get("actor"),
        role=state.get("role"),
        input_preview=json.dumps(validated.model_dump(exclude={"actor", "role"}), default=str)[:1500],
        metadata={"flow": "agent", "step": "tool", "tool": "submit_intake_report"},
    ) as span:
        raw = _tools()["submit_intake_report"].invoke(validated.model_dump())
        data = json.loads(raw) if isinstance(raw, str) else raw
        if not data.get("ok", True):
            err = data.get("error") or "submit_intake_report failed"
            span.set_output(data)
            return {
                **state,
                "response": str(err),
                "details": {"route": "intake", "error": err},
            }
        created = data.get("report") or data
        span.set_output(created)
        span.update(tool="submit_intake_report", reference_id=created.get("reference_id"))
    fallback = f"Created intake report {created['reference_id']} (status=New)."
    return {
        **state,
        "response": draft_user_response(
            kind="intake_created",
            user_message=state.get("message", ""),
            facts=facts_json({"report": created}),
            fallback=fallback,
            actor=state.get("actor"),
            role=state.get("role"),
            history=state.get("chat_history"),
        ),
        "details": {"route": "intake", "report": created},
        "halted": False,
    }


def _ref_from_history(history: list[dict[str, str]] | None) -> str | None:
    if not history:
        return None
    for turn in reversed(history[-8:]):
        content = str(turn.get("content") or "")
        m = re.search(r"REF-\d{4}-\d{4}", content, flags=re.IGNORECASE)
        if m:
            return m.group(0).upper()
    return None


def lookup_node(state: AgentState) -> AgentState:
    msg = _normalize_message(state.get("message", ""))
    soft = _soft_message(msg)
    ref = None
    m = re.search(r"REF-\d{4}-\d{4}", msg, flags=re.IGNORECASE)
    if m:
        ref = m.group(0).upper()
    elif _is_status_inquiry(soft) and not _is_lot_lookup_request(soft):
        # "actually it's closed" / "wrong status" → re-fetch last REF from chat
        ref = _ref_from_history(state.get("chat_history"))
    if ref:
        tracer = get_container().tracer
        with tracer.span(
            "agent_tool_get_report",
            kind="tool",
            actor=state.get("actor"),
            role=state.get("role"),
            input_preview=ref,
            metadata={"flow": "agent", "step": "tool", "tool": "get_report", "reference_id": ref},
        ) as span:
            raw = _tools()["get_report"].invoke({"reference_id": ref})
            data = json.loads(raw)
            span.set_output(data)
            span.update(tool="get_report", found=bool(data.get("ok")))
        if not data.get("ok"):
            fallback = f"Report {ref} not found."
            return {
                **state,
                "response": draft_user_response(
                    kind="lookup_not_found",
                    user_message=msg,
                    facts=fallback,
                    fallback=fallback,
                    actor=state.get("actor"),
                    role=state.get("role"),
                    history=state.get("chat_history"),
                ),
                "details": {"route": "lookup"},
            }
        fallback = f"Report {ref}: {json.dumps(data['report'], indent=2)}"
        return {
            **state,
            "response": draft_user_response(
                kind="lookup_one",
                user_message=msg,
                facts=facts_json({"report": data["report"]}),
                fallback=fallback,
                actor=state.get("actor"),
                role=state.get("role"),
                history=state.get("chat_history"),
            ),
            "details": {"route": "lookup", "report": data["report"]},
        }

    lot_m = _LOT_TOKEN_RE.search(msg)
    lot = lot_m.group(0).upper() if lot_m else None
    list_args: dict[str, Any] = {}
    if lot:
        list_args["batch_lot_number"] = lot

    tracer = get_container().tracer
    with tracer.span(
        "agent_tool_list_reports",
        kind="tool",
        actor=state.get("actor"),
        role=state.get("role"),
        input_preview=json.dumps(list_args) if list_args else "list_reports",
        metadata={
            "flow": "agent",
            "step": "tool",
            "tool": "list_reports",
            "batch_lot_number": lot,
        },
    ) as span:
        raw = _tools()["list_reports"].invoke(list_args)
        data = json.loads(raw)
        span.set_output({"count": data.get("count", 0), "batch_lot_number": lot})
        span.update(tool="list_reports", count=data.get("count", 0))

    reports = data.get("reports", [])[:15]
    if lot and not reports:
        format_note = ""
        if not LOT_RE.match(lot):
            format_note = (
                f"\n\nNote: `{lot}` does not match **LOT-#####** (exactly 5 digits), "
                "so it cannot be used for intake create either."
            )
        fallback = (
            f"### {lot} — no reports found\n\n"
            f"The intake database has no Product Quality Complaint or Adverse Event "
            f"records for `{lot}`."
            f"{format_note}"
        )
        return {
            **state,
            "response": draft_user_response(
                kind="lookup_not_found",
                user_message=msg,
                facts=fallback,
                fallback=fallback,
                actor=state.get("actor"),
                role=state.get("role"),
                history=state.get("chat_history"),
            ),
            "details": {"route": "lookup", "batch_lot_number": lot, "count": 0},
        }

    if lot and len(reports) == 1:
        report = reports[0]
        fallback = f"Report {report.get('reference_id')}: {json.dumps(report, indent=2)}"
        return {
            **state,
            "response": draft_user_response(
                kind="lookup_one",
                user_message=msg,
                facts=facts_json({"report": report}),
                fallback=fallback,
                actor=state.get("actor"),
                role=state.get("role"),
                history=state.get("chat_history"),
            ),
            "details": {"route": "lookup", "report": report, "batch_lot_number": lot},
        }

    summary = [
        f"{r['reference_id']} | {r['status']} | {r['product_name']} | {r['batch_lot_number']}"
        for r in reports
    ]
    heading = f"Reports for {lot}:" if lot else "Recent reports:"
    fallback = heading + "\n" + ("\n".join(summary) if summary else "No reports yet.")
    return {
        **state,
        "response": draft_user_response(
            kind="lookup_list",
            user_message=msg,
            facts=facts_json({"count": data.get("count", 0), "reports": reports, "batch_lot_number": lot}),
            fallback=fallback,
            actor=state.get("actor"),
            role=state.get("role"),
            history=state.get("chat_history"),
        ),
        "details": {
            "route": "lookup",
            "count": data.get("count", 0),
            "batch_lot_number": lot,
            "reports": reports,
        },
    }


def status_node(state: AgentState) -> AgentState:
    msg = state.get("message", "")
    soft = _normalize_status_soft(msg)
    # Safety: never treat a read-only status question as an update
    if _is_status_inquiry(soft) and not _is_status_change_request(soft):
        return lookup_node(state)

    role = state.get("role") or "operator"
    # Match REST API: status changes require workflow:update (admin/reviewer).
    # Approvers finish pending closes via /agent/hitl/.../resolve, not chat mutations.
    if not has_permission(role, "workflow:update"):
        fallback = (
            f"Your role (`{role}`) cannot change report status. "
            "Ask a reviewer/admin, or use lookup to check status."
        )
        return {
            **state,
            "response": fallback,
            "details": {"route": "status", "denied": True},
        }

    # Agent decides args from the user message (+ recent REF in chat).
    # Ignore client tool_args — sticky JSON from the UI caused wrong Closed updates.
    args: dict[str, Any] = {}
    parsed = _extract_json_blob(msg)
    if parsed and parsed.get("reference_id") and parsed.get("new_status"):
        canon = _canonical_status(str(parsed.get("new_status")))
        if not canon:
            fallback = (
                "Valid statuses are only **New**, **In Review**, and **Closed**. "
                "There is no separate 'Review Completed' status — say *start the review* "
                "or *complete the review / move to approver* (requests close for HITL)."
            )
            return {
                **state,
                "response": fallback,
                "details": {"route": "status", "needs_args": True, "invalid_status": parsed.get("new_status")},
            }
        args = {"reference_id": str(parsed["reference_id"]).upper(), "new_status": canon}
        if parsed.get("reviewer_notes"):
            args["reviewer_notes"] = str(parsed["reviewer_notes"]).strip()
    else:
        ref_m = re.search(r"REF-\d{4}-\d{4}", msg, flags=re.IGNORECASE)
        ref = ref_m.group(0).upper() if ref_m else _ref_from_history(state.get("chat_history"))
        new_status = _infer_new_status(soft)
        if not ref or not new_status:
            fallback = (
                "I can change status from your message alone — no tool args needed.\n\n"
                "Valid workflow: **New → In Review → Closed** (closing needs approver HITL).\n"
                "Examples:\n"
                "- Start the review of REF-2026-0001\n"
                "- Move REF-2026-0001 to In Review\n"
                "- Complete the review of REF-2026-0003 — notes: packaging intact, lot verified\n"
                "- Move to approver (uses the last REF in this chat; include reviewer notes)\n"
                "- Request close for REF-2026-0003 — notes: everything checked"
            )
            return {
                **state,
                "response": fallback,
                "details": {"route": "status", "needs_args": True},
            }
        args = {"reference_id": ref, "new_status": new_status}

    # Reviewer notes for close request (JSON notes / notes: / trailing "with details…")
    if not args.get("reviewer_notes"):
        extracted = _extract_reviewer_notes(msg)
        if extracted:
            args["reviewer_notes"] = extracted

    args["actor"] = state.get("actor", "operator")
    args["role"] = state.get("role", "operator")
    signature = str(sorted((k, str(v)) for k, v in args.items() if k not in {"actor", "role"}))
    try:
        validated = UpdateStatusInput(**args)
    except ValidationError as exc:
        if _breaker.record_failure("update_status", signature):
            fallback = "Circuit breaker open: repeated invalid update_status arguments."
            return {
                **state,
                "response": draft_user_response(
                    kind="status_circuit_breaker",
                    user_message=state.get("message", ""),
                    facts=facts_json({"errors": exc.errors(), "halted": True}),
                    fallback=fallback,
                    actor=state.get("actor"),
                    role=state.get("role"),
                    history=state.get("chat_history"),
                ),
                "halted": True,
                "details": {"route": "status", "errors": exc.errors()},
            }
        fallback = "Validation failed for update_status."
        return {
            **state,
            "response": draft_user_response(
                kind="status_validation_error",
                user_message=state.get("message", ""),
                facts=facts_json({"errors": exc.errors()}),
                fallback=fallback,
                actor=state.get("actor"),
                role=state.get("role"),
                history=state.get("chat_history"),
            ),
            "details": {"route": "status", "errors": exc.errors()},
        }

    # HITL gate for close — reviewer must supply triage notes for the approver
    if validated.new_status == "Closed":
        if not (validated.reviewer_notes or "").strip():
            # Allow if report already has notes from an earlier triage step
            try:
                existing = _reports.get(validated.reference_id)
            except KeyError:
                existing = {}
            if not (existing.get("reviewer_notes") or "").strip():
                fallback = (
                    f"To request close for **{validated.reference_id}**, add **reviewer notes** "
                    "for the approver (what you checked, findings, recommendation).\n\n"
                    "Example: `Request close for REF-2026-0001 — notes: Lot verified, "
                    "packaging photos reviewed, recommend close.`"
                )
                return {
                    **state,
                    "response": fallback,
                    "details": {"route": "status", "needs_args": True, "needs_reviewer_notes": True},
                }

        try:
            pending = _reports.request_status(
                validated.reference_id,
                "Closed",
                validated.actor,
                validated.role,
                reviewer_notes=validated.reviewer_notes,
            )
        except Exception as exc:  # noqa: BLE001
            fallback = f"Cannot request close: {exc}"
            return {
                **state,
                "response": draft_user_response(
                    kind="status_close_error",
                    user_message=state.get("message", ""),
                    facts=fallback,
                    fallback=fallback,
                    actor=state.get("actor"),
                    role=state.get("role"),
                    history=state.get("chat_history"),
                ),
                "details": {"route": "status", "error": str(exc)},
            }

        tracer = get_container().tracer
        session_id, thread_id = _hitl_session_thread(state)
        with tracer.span(
            "agent_hitl_close_request",
            kind="tool",
            actor=state.get("actor"),
            role=state.get("role"),
            input_preview=validated.reference_id,
            metadata={
                "flow": "agent",
                "step": "hitl",
                "tool": "approve_close",
                "reference_id": validated.reference_id,
                "session_id": session_id,
                "thread_id": thread_id,
            },
        ) as span:
            # Interrupt re-runs this node from the top — reuse pending HITL for the REF.
            hitl = _chat.find_pending_hitl_for_reference(validated.reference_id)
            if not hitl:
                hitl = _chat.create_hitl(
                    session_id=session_id,
                    thread_id=thread_id,
                    username=state.get("actor", ""),
                    tool_name="approve_close",
                    payload={
                        "reference_id": validated.reference_id,
                        "actor": validated.actor,
                        "role": validated.role,
                        "report": pending,
                    },
                )
            elif (not hitl.get("session_id") or not hitl.get("thread_id")) and (
                session_id or thread_id
            ):
                hitl = _chat.backfill_hitl_context(
                    hitl["request_id"], session_id=session_id or None, thread_id=thread_id or None
                )
            span.set_output(hitl)
            span.update(hitl_request_id=hitl.get("request_id"), pending_close=True)

        # Admin / approver may complete close immediately when self-approve is allowed.
        can_auto_approve = (
            pending.get("pending_close")
            and has_permission(validated.role, "workflow:approve_close")
            and get_settings().allow_self_approve
        )
        if can_auto_approve:
            closed = json.loads(
                invoke_approve_close(validated.reference_id, validated.actor, validated.role)
            )
            try:
                _chat.resolve_hitl(
                    hitl["request_id"],
                    approved=True,
                    resolved_by=validated.actor,
                    note="Auto-approved by role with workflow:approve_close",
                )
            except Exception:  # noqa: BLE001
                pass
            fallback = (
                f"Close approved for **{validated.reference_id}** "
                f"(you have approve permission as `{validated.role}`). Status is now **Closed**."
            )
            return {
                **state,
                "response": draft_user_response(
                    kind="status_hitl_approved",
                    user_message=state.get("message", ""),
                    facts=facts_json(
                        {
                            "reference_id": validated.reference_id,
                            "approved": True,
                            "auto_approved": True,
                            "report": closed.get("report"),
                            "resolved_by": validated.actor,
                            "hitl_request_id": hitl["request_id"],
                        }
                    ),
                    fallback=fallback,
                    actor=state.get("actor"),
                    role=state.get("role"),
                    history=state.get("chat_history"),
                ),
                "needs_hitl": False,
                "hitl_request_id": hitl["request_id"],
                "details": {
                    "route": "status",
                    "approved": True,
                    "auto_approved": True,
                    "report": closed.get("report"),
                },
            }

        # Operators / reviewers: pause until an approver resumes
        decision = interrupt(
            {
                "type": "hitl_close_approval",
                "hitl_request_id": hitl["request_id"],
                "reference_id": validated.reference_id,
                "message": f"Approve closing {validated.reference_id}?",
            }
        )
        approved = bool(decision.get("approved")) if isinstance(decision, dict) else bool(decision)
        resolver = (
            decision.get("resolved_by", validated.actor)
            if isinstance(decision, dict)
            else validated.actor
        )
        decision_note = (
            str(decision.get("note") or "").strip() if isinstance(decision, dict) else ""
        )
        if not approved:
            try:
                rejected = _reports.reject_close(
                    validated.reference_id, resolver, "approver", note=decision_note or None
                )
            except Exception:  # noqa: BLE001
                rejected = pending
            fallback = f"Close rejected for {validated.reference_id}. Remains In Review."
            return {
                **state,
                "response": draft_user_response(
                    kind="status_hitl_rejected",
                    user_message=state.get("message", ""),
                    facts=facts_json(
                        {
                            "reference_id": validated.reference_id,
                            "approved": False,
                            "report": rejected,
                            "approver_comment": decision_note or None,
                            "hitl_request_id": hitl["request_id"],
                        }
                    ),
                    fallback=fallback,
                    actor=state.get("actor"),
                    role=state.get("role"),
                    history=state.get("chat_history"),
                ),
                "needs_hitl": True,
                "hitl_request_id": hitl["request_id"],
                "details": {"route": "status", "approved": False, "report": rejected},
            }
        closed = json.loads(
            invoke_approve_close(
                validated.reference_id, resolver, "approver", comment=decision_note or None
            )
        )
        fallback = f"HITL approved. Closed {validated.reference_id}."
        return {
            **state,
            "response": draft_user_response(
                kind="status_hitl_approved",
                user_message=state.get("message", ""),
                facts=facts_json(
                    {
                        "reference_id": validated.reference_id,
                        "approved": True,
                        "report": closed.get("report"),
                        "resolved_by": resolver,
                        "approver_comment": decision_note or None,
                    }
                ),
                fallback=fallback,
                actor=state.get("actor"),
                role=state.get("role"),
                history=state.get("chat_history"),
            ),
            "needs_hitl": False,
            "hitl_request_id": hitl["request_id"],
            "details": {"route": "status", "approved": True, "report": closed.get("report")},
        }

    _breaker.reset("update_status", signature)
    tracer = get_container().tracer
    try:
        with tracer.span(
            "agent_tool_update_status",
            kind="tool",
            actor=state.get("actor"),
            role=state.get("role"),
            input_preview=f"{validated.reference_id} -> {validated.new_status}",
            metadata={
                "flow": "agent",
                "step": "tool",
                "tool": "update_status",
                "reference_id": validated.reference_id,
                "new_status": validated.new_status,
            },
        ) as span:
            raw = _tools()["update_status"].invoke(validated.model_dump())
            data = json.loads(raw) if isinstance(raw, str) else raw
            if not data.get("ok", True):
                err = data.get("error") or "update_status failed"
                span.set_output(data)
                raise ValueError(str(err))
            result = data.get("report") or data
            span.set_output(result)
            span.update(tool="update_status", status=result.get("status"))
    except KeyError:
        fallback = f"Report {validated.reference_id} was not found."
        return {
            **state,
            "response": fallback,
            "details": {"route": "status", "error": "not_found"},
        }
    except ValueError as exc:
        fallback = (
            f"Cannot update **{validated.reference_id}** to **{validated.new_status}**: {exc}\n\n"
            "Valid path: **New → In Review → Closed**."
        )
        return {
            **state,
            "response": fallback,
            "details": {"route": "status", "error": str(exc)},
        }

    fallback = (
        f"### {validated.reference_id}\n\n"
        f"- **Status:** {result.get('status')}\n"
        f"- **Updated by:** {result.get('updated_by') or validated.actor}"
    )
    return {
        **state,
        "response": draft_user_response(
            kind="status_updated",
            user_message=state.get("message", ""),
            facts=facts_json({"report": result}),
            fallback=fallback,
            actor=state.get("actor"),
            role=state.get("role"),
            history=state.get("chat_history"),
        ),
        "details": {"route": "status", "report": result},
    }


def route_after_router(state: AgentState) -> str:
    intent = state.get("intent", "rag")
    mapping = {
        "direct": "direct",
        "rag": "rag",
        "intake": "intake",
        "status": "status",
        "lookup": "lookup",
    }
    return mapping.get(intent, "rag")


def build_agent_graph():
    graph = StateGraph(AgentState)
    graph.add_node("router", router_node)
    graph.add_node("direct", direct_node)
    graph.add_node("rag", rag_node)
    graph.add_node("intake", intake_node)
    graph.add_node("status", status_node)
    graph.add_node("lookup", lookup_node)

    graph.set_entry_point("router")
    graph.add_conditional_edges(
        "router",
        route_after_router,
        {
            "direct": "direct",
            "rag": "rag",
            "intake": "intake",
            "status": "status",
            "lookup": "lookup",
        },
    )
    for node in ("direct", "rag", "intake", "status", "lookup"):
        graph.add_edge(node, END)

    checkpointer = get_checkpointer()
    return graph.compile(checkpointer=checkpointer)


_GRAPH = None


def get_agent_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_agent_graph()
    return _GRAPH


class LangGraphAgentService:
    """Facade used by API layer."""

    def __init__(self) -> None:
        self.graph = get_agent_graph()
        self.chat_svc = ChatHistoryService()

    def _history_for_prompt(self, session_id: str, username: str) -> list[dict[str, str]]:
        msgs = self.chat_svc.list_messages(session_id, username, limit=20)
        return [{"role": m["role"], "content": m["content"]} for m in msgs if m["role"] in {"user", "assistant"}]

    def chat(
        self,
        *,
        session_id: str,
        message: str,
        actor: str,
        role: str,
        tool_args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = self.chat_svc.get_session(session_id, username=actor)
        thread_id = str(session.get("thread_id") or "").strip()
        if not thread_id:
            raise ValueError(f"Chat session {session_id} is missing a LangGraph thread_id")

        self.chat_svc.add_message(session_id=session_id, username=actor, role="user", content=message)
        history = self._history_for_prompt(session_id, actor)

        config = {"configurable": {"thread_id": thread_id}}
        state: AgentState = {
            "message": message,
            "actor": actor,
            "role": role,
            "session_id": session_id,
            "thread_id": thread_id,
            # FE no longer sends tool_args. Status/lookup always parse NL + history.
            # Intake may still accept explicit tool_args from API/tests.
            "tool_args": tool_args or {},
            "chat_history": history,
            "halted": False,
            "needs_hitl": False,
        }
        tracer = get_container().tracer
        with tracer.span(
            "agent_chat",
            kind="span",
            actor=actor,
            role=role,
            input_preview=message,
            metadata={
                "flow": "agent",
                "session_id": session_id,
                "thread_id": thread_id,
            },
        ) as root:
            result = self.graph.invoke(state, config=config)

            # Interrupted for HITL?
            if isinstance(result, dict) and result.get("__interrupt__"):
                interrupt_payload = result["__interrupt__"]
                first = interrupt_payload[0] if interrupt_payload else None
                info = getattr(first, "value", first) if first is not None else {}
                if not isinstance(info, dict):
                    info = {"message": str(info)}
                hitl_id = info.get("hitl_request_id")
                fallback = (
                    f"Paused for human approval ({hitl_id}). "
                    f"{info.get('message') or 'Awaiting HITL.'}"
                )
                response = draft_user_response(
                    kind="status_hitl_pending",
                    user_message=message,
                    facts=facts_json(info),
                    fallback=fallback,
                    actor=actor,
                    role=role,
                    history=history,
                )
                self.chat_svc.add_message(
                    session_id=session_id,
                    username=actor,
                    role="assistant",
                    content=response,
                    intent="status",
                    metadata={"hitl": info, "interrupted": True},
                )
                root.set_output({"interrupted": True, "hitl": info, "response_preview": response[:800]})
                root.update(intent="status", interrupted=True, hitl_request_id=hitl_id)
                return {
                    "session_id": session_id,
                    "thread_id": thread_id,
                    "intent": "status",
                    "response": response,
                    "interrupted": True,
                    "hitl": info,
                    "details": {},
                    "trace_id": root.trace_id,
                }

            response = result.get("response") or "No response."
            intent = result.get("intent")
            self.chat_svc.add_message(
                session_id=session_id,
                username=actor,
                role="assistant",
                content=response,
                intent=intent,
                metadata=result.get("details") or {},
            )
            root.set_output(
                {
                    "intent": intent,
                    "response_preview": (response or "")[:1000],
                    "route_meta": result.get("route_meta"),
                    "details_keys": list((result.get("details") or {}).keys()),
                }
            )
            root.update(
                intent=intent,
                interrupted=False,
                halted=bool(result.get("halted")),
                router_source=(result.get("route_meta") or {}).get("router_source"),
            )
            return {
                "session_id": session_id,
                "thread_id": thread_id,
                "intent": intent,
                "response": response,
                "interrupted": False,
                "halted": bool(result.get("halted")),
                "details": result.get("details") or {},
                "hitl_request_id": result.get("hitl_request_id"),
                "trace_id": root.trace_id,
            }

    def resume_hitl(
        self,
        *,
        request_id: str,
        approved: bool,
        resolved_by: str,
        note: str | None = None,
    ) -> dict[str, Any]:
        tracer = get_container().tracer
        with tracer.span(
            "agent_hitl_resume",
            kind="span",
            actor=resolved_by,
            role="approver",
            input_preview=request_id,
            metadata={
                "flow": "agent",
                "step": "hitl_resume",
                "approved": approved,
                "request_id": request_id,
            },
        ) as root:
            # Load first — do NOT mark resolved until the close decision is applied.
            pending = self.chat_svc.get_hitl(request_id)
            if pending.get("status") != "pending":
                raise ValueError(f"HITL request already {pending.get('status')}")

            payload = pending.get("payload") or {}
            reference_id = str(payload.get("reference_id") or "").strip().upper()
            if not reference_id:
                raise ValueError("HITL payload missing reference_id")

            thread_id = str(pending.get("thread_id") or "").strip()
            session_id = str(pending.get("session_id") or "").strip()
            resume_payload = {
                "approved": approved,
                "resolved_by": resolved_by,
                "note": note,
            }

            applied_via = "report_service"
            result: dict[str, Any] = {}
            if thread_id and _thread_has_pending_interrupt(thread_id):
                try:
                    raw = self.graph.invoke(
                        Command(resume=resume_payload),
                        config={"configurable": {"thread_id": thread_id}},
                    )
                    result = raw if isinstance(raw, dict) else {"response": str(raw)}
                    # Verify the report actually moved; otherwise fall back.
                    report_after = _reports.get(reference_id)
                    close_applied = (
                        report_after.get("status") == "Closed"
                        if approved
                        else (
                            report_after.get("status") == "In Review"
                            and not report_after.get("pending_close")
                        )
                    )
                    if close_applied:
                        applied_via = "graph"
                        if isinstance(result, dict):
                            details = dict(result.get("details") or {})
                            details["applied_via"] = "graph"
                            details.setdefault("report", report_after)
                            result["details"] = details
                    else:
                        logger.warning(
                            "hitl_graph_resume_no_effect",
                            request_id=request_id,
                            thread_id=thread_id,
                            reference_id=reference_id,
                        )
                        applied_via = "report_service"
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "hitl_graph_resume_failed",
                        request_id=request_id,
                        thread_id=thread_id,
                        error=str(exc),
                    )
                    applied_via = "report_service"

            if applied_via == "report_service":
                try:
                    if approved:
                        report = _reports.approve_close(
                            reference_id, resolved_by, "approver", comment=note
                        )
                        response = f"HITL approved. Closed {reference_id}."
                    else:
                        report = _reports.reject_close(
                            reference_id, resolved_by, "approver", note=note
                        )
                        response = f"Close rejected for {reference_id}. Remains In Review."
                except ValueError as exc:
                    # Partial graph resume may have already applied the decision.
                    report = _reports.get(reference_id)
                    if approved and report.get("status") == "Closed":
                        response = f"HITL approved. Closed {reference_id}."
                    elif not approved and report.get("status") == "In Review" and not report.get(
                        "pending_close"
                    ):
                        response = f"Close rejected for {reference_id}. Remains In Review."
                    else:
                        raise exc
                result = {
                    "response": response,
                    "details": {
                        "route": "status",
                        "approved": approved,
                        "report": report,
                        "applied_via": "report_service",
                    },
                }

            hitl = self.chat_svc.resolve_hitl(
                request_id, approved=approved, resolved_by=resolved_by, note=note
            )
            # Clear any duplicate pending rows for the same REF (interrupt re-entry orphans)
            self.chat_svc.resolve_pending_for_reference(
                reference_id,
                approved=approved,
                resolved_by=resolved_by,
                note=note or f"Synced with {request_id}",
            )

            response = (
                result.get("response")
                if isinstance(result, dict)
                else str(result)
            ) or "HITL resolved."
            owner = hitl.get("username") or resolved_by
            if session_id:
                try:
                    self.chat_svc.add_message(
                        session_id=session_id,
                        username=owner,
                        role="assistant",
                        content=response,
                        intent="status",
                        metadata={
                            "hitl_resolution": hitl,
                            "approved": approved,
                            "applied_via": applied_via,
                        },
                    )
                    self.chat_svc.add_message(
                        session_id=session_id,
                        username=owner,
                        role="system",
                        content=(
                            f"HITL {request_id} "
                            f"{'approved' if approved else 'rejected'} by {resolved_by}"
                        ),
                        intent="hitl",
                        metadata={"request_id": request_id, "approved": approved},
                    )
                except KeyError:
                    logger.warning(
                        "hitl_chat_append_skipped",
                        request_id=request_id,
                        session_id=session_id,
                    )

            details = result.get("details") if isinstance(result, dict) else {}
            if isinstance(details, dict):
                details = {**details, "applied_via": applied_via}
            root.set_output(
                {
                    "approved": approved,
                    "applied_via": applied_via,
                    "response_preview": (response or "")[:800],
                }
            )
            root.update(session_id=session_id, thread_id=thread_id, applied_via=applied_via)
            return {
                "hitl": hitl,
                "response": response,
                "session_id": session_id,
                "thread_id": thread_id,
                "details": details,
                "trace_id": root.trace_id,
            }

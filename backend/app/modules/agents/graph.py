"""LangGraph router agent with tools, chat-aware state, and HITL interrupt."""

from __future__ import annotations

import json
import re
from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.types import Command, interrupt
from pydantic import ValidationError

from app.auth.roles import has_permission
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
    SubmitIntakeInput,
    UpdateStatusInput,
)
from app.services.chat_service import ChatHistoryService
from app.services.report_service import ReportService

logger = get_logger("langgraph_agent")

Intent = Literal["direct", "rag", "intake", "status", "lookup", "unknown"]


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
    if s in {"closed", "close", "closing"}:
        return "Closed"
    if s in {"new"}:
        return "New"
    if s in {
        "in review",
        "review",
        "under review",
        "review completed",
        "review complete",
        "review is completed",
        "review is complete",
        "start review",
        "start the review",
    }:
        # Never invent "Review Completed" — only New / In Review / Closed exist
        return "In Review"
    if raw in _ALLOWED_STATUSES:
        return raw
    return None


def _infer_new_status(soft: str) -> str | None:
    """Map natural-language change phrases to workflow status. Never invent extra statuses."""
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
            "to in review",
        )
    ):
        return "In Review"
    if re.search(r"\bclose\b", soft):
        return "Closed"
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
    text = message.lower().strip()
    # Normalize punctuation so "hi," / "hello!" still count as social
    soft = re.sub(r"[^\w\s\-]", " ", text)
    soft = re.sub(r"\s+", " ", soft).strip()

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
    if any(
        k in soft
        for k in [
            "create",
            "submit",
            "intake",
            "new report",
            "file a",
            "log a",
            "open a suspected",
            "open an adverse",
        ]
    ):
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
    soft = re.sub(r"\s+", " ", re.sub(r"[^\w\s\-]", " ", message.lower())).strip()
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
        # or invent status changes from sticky/ambiguous phrasing.
        if _is_status_inquiry(soft) and not _is_status_change_request(soft):
            intent = "lookup"
            route_meta = {"router_source": "rules_safe", "intent": intent}
        elif _is_status_change_request(soft):
            intent = "status"
            route_meta = {"router_source": "rules_safe", "intent": intent}
        elif re.search(r"lot-\d{5}", soft) and any(
            k in soft for k in ("what should", "packaging", "quarantine", "sop", "how do", "complaint")
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
        # Try parse JSON from message; else ask for fields
        parsed = _extract_json_blob(state.get("message", ""))
        if parsed:
            args = parsed
        else:
            fallback = (
                "To create an intake report, include the fields in your message "
                "(or paste a JSON object). Needed: report_type, product_name, "
                "batch_lot_number (LOT-#####), date_received, reporter_type, description "
                "(+ event fields for AE)."
            )
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
                "details": {"route": "intake", "needs_args": True},
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
        fallback = "Validation failed for submit_intake_report."
        return {
            **state,
            "response": draft_user_response(
                kind="intake_validation_error",
                user_message=state.get("message", ""),
                facts=facts_json({"errors": exc.errors()}),
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
    msg = state.get("message", "")
    ref = None
    m = re.search(r"REF-\d{4}-\d{4}", msg, flags=re.IGNORECASE)
    if m:
        ref = m.group(0).upper()
    elif _is_status_inquiry(re.sub(r"\s+", " ", re.sub(r"[^\w\s\-]", " ", msg.lower()))):
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

    tracer = get_container().tracer
    with tracer.span(
        "agent_tool_list_reports",
        kind="tool",
        actor=state.get("actor"),
        role=state.get("role"),
        input_preview="list_reports",
        metadata={"flow": "agent", "step": "tool", "tool": "list_reports"},
    ) as span:
        raw = _tools()["list_reports"].invoke({})
        data = json.loads(raw)
        span.set_output({"count": data.get("count", 0)})
        span.update(tool="list_reports", count=data.get("count", 0))
    summary = [
        f"{r['reference_id']} | {r['status']} | {r['product_name']} | {r['batch_lot_number']}"
        for r in data.get("reports", [])[:15]
    ]
    fallback = "Recent reports:\n" + ("\n".join(summary) if summary else "No reports yet.")
    return {
        **state,
        "response": draft_user_response(
            kind="lookup_list",
            user_message=msg,
            facts=facts_json({"count": data.get("count", 0), "reports": data.get("reports", [])[:15]}),
            fallback=fallback,
            actor=state.get("actor"),
            role=state.get("role"),
            history=state.get("chat_history"),
        ),
        "details": {"route": "lookup", "count": data.get("count", 0)},
    }


def status_node(state: AgentState) -> AgentState:
    msg = state.get("message", "")
    soft = re.sub(r"\s+", " ", re.sub(r"[^\w\s\-]", " ", msg.lower())).strip()
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
                "There is no 'Review Completed' status — say *start the review* or *close it*."
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
                "Valid workflow: **New → In Review → Closed** (no other statuses).\n"
                "Examples:\n"
                "- Start the review of REF-2026-0001\n"
                "- Move REF-2026-0001 to In Review\n"
                "- Request close for REF-2026-0003 — notes: packaging intact, lot verified\n"
                "- Close it (uses the last REF in this chat; include reviewer notes)"
            )
            return {
                **state,
                "response": fallback,
                "details": {"route": "status", "needs_args": True},
            }
        args = {"reference_id": ref, "new_status": new_status}

    # Reviewer notes for close request (JSON notes / "notes:" clause / free text after dash)
    if not args.get("reviewer_notes"):
        notes_m = re.search(
            r"(?:reviewer[_\s-]?notes|notes|triage)\s*[:=]\s*(.+)$",
            msg,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if notes_m:
            args["reviewer_notes"] = notes_m.group(1).strip().strip("`\"'")

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
            },
        ) as span:
            hitl = _chat.create_hitl(
                session_id=state.get("session_id", ""),
                thread_id=state.get("thread_id", ""),
                username=state.get("actor", ""),
                tool_name="approve_close",
                payload={
                    "reference_id": validated.reference_id,
                    "actor": validated.actor,
                    "role": validated.role,
                    "report": pending,
                },
            )
            span.set_output(hitl)
            span.update(hitl_request_id=hitl.get("request_id"), pending_close=True)

        # Admin / approver may complete close immediately (they hold workflow:approve_close).
        if pending.get("pending_close") and has_permission(validated.role, "workflow:approve_close"):
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
        thread_id = session["thread_id"]

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
            hitl = self.chat_svc.resolve_hitl(
                request_id, approved=approved, resolved_by=resolved_by, note=note
            )
            thread_id = hitl["thread_id"]
            session_id = hitl["session_id"]
            config = {"configurable": {"thread_id": thread_id}}
            result = self.graph.invoke(
                Command(resume={"approved": approved, "resolved_by": resolved_by, "note": note}),
                config=config,
            )
            response = result.get("response") if isinstance(result, dict) else str(result)
            owner = hitl.get("username") or resolved_by
            self.chat_svc.add_message(
                session_id=session_id,
                username=owner,
                role="assistant",
                content=response or "HITL resolved.",
                intent="status",
                metadata={"hitl_resolution": hitl, "approved": approved},
            )
            # Also system note from resolver
            self.chat_svc.add_message(
                session_id=session_id,
                username=owner,
                role="system",
                content=f"HITL {request_id} {'approved' if approved else 'rejected'} by {resolved_by}",
                intent="hitl",
                metadata={"request_id": request_id, "approved": approved},
            )
            root.set_output({"approved": approved, "response_preview": (response or "")[:800]})
            root.update(session_id=session_id, thread_id=thread_id)
            return {
                "hitl": hitl,
                "response": response,
                "session_id": session_id,
                "thread_id": thread_id,
                "details": result.get("details") if isinstance(result, dict) else {},
                "trace_id": root.trace_id,
            }

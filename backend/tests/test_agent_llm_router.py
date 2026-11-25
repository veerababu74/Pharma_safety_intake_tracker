"""LLM-first router: guards, confirmation flow, grounding, timeout fallback.

The LLM is replaced by fixed RouteDecisions so these tests are deterministic.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

import app.modules.agents.graph as g
from app.db.session import db_manager
from app.modules.agents.graph import RouteDecision, router_node, status_node
from app.services.report_service import ReportService


def setup_module():
    db_manager.init()


def _llm(monkeypatch, **decision):
    monkeypatch.setattr(g, "_llm_route", lambda m, h: (RouteDecision(**decision), {"router_source": "llm"}))


def _route(message, history=None, pending=None, role="reviewer"):
    return router_node(
        {
            "message": message,
            "actor": role,
            "role": role,
            "chat_history": history or [],
            "pending_action": pending or {},
        }
    )


def _new_report(desc: str) -> str:
    return ReportService().create(
        {
            "report_type": "Product Quality Complaint",
            "product_name": "NeuroCalm 50mg",
            "batch_lot_number": "LOT-88392",
            "date_received": "2026-03-01",
            "reporter_type": "Consumer",
            "description": desc,
        },
        actor="reviewer",
        role="reviewer",
    )["reference_id"]


# --- guards --------------------------------------------------------------------


def test_llm_status_on_question_is_downgraded_to_lookup(monkeypatch):
    _llm(monkeypatch, intent="status", action="request_close", reference_id="REF-2026-0159", confidence=0.99)
    out = _route("did the review complete for REF-2026-0159")
    assert out["intent"] == "lookup"
    assert out["route_meta"]["router_source"] == "guard_question_no_write"


def test_llm_intake_on_question_is_downgraded_to_rag(monkeypatch):
    _llm(monkeypatch, intent="intake", confidence=0.95)
    assert _route("how do I submit an intake")["intent"] == "rag"


def test_write_runs_when_llm_and_rules_agree(monkeypatch):
    _llm(monkeypatch, intent="status", action="start_review", reference_id="REF-2026-0159", confidence=0.95)
    out = _route("start the review of REF-2026-0159")
    assert out["intent"] == "status"
    assert out["route_meta"]["router_source"] == "llm_rules_agree"


def test_low_confidence_write_asks_for_confirmation(monkeypatch):
    _llm(monkeypatch, intent="status", action="start_review", reference_id="REF-2026-0159", confidence=0.4)
    out = _route("start the review of REF-2026-0159")
    assert out["intent"] == "clarify"
    assert out["pending_action_out"]["forced_args"]["new_status"] == "In Review"


def test_unseen_phrasing_llm_write_rules_disagree_asks_confirmation(monkeypatch):
    _llm(monkeypatch, intent="status", action="start_review", reference_id="REF-2026-0159", confidence=0.9)
    out = _route("I'll pick up REF-2026-0159 now")
    assert out["intent"] == "clarify"
    fa = out["pending_action_out"]["forced_args"]
    assert fa["reference_id"] == "REF-2026-0159" and fa["new_status"] == "In Review"
    assert "yes" in out["response"].lower()


def test_rules_write_but_llm_read_asks_confirmation(monkeypatch):
    _llm(monkeypatch, intent="lookup", reference_id="REF-2026-0159", confidence=0.8)
    out = _route("close REF-2026-0159")
    assert out["intent"] == "clarify"
    assert out["pending_action_out"]["forced_args"]["new_status"] == "Closed"


def test_llm_handles_queue_phrasing_rules_miss(monkeypatch):
    _llm(monkeypatch, intent="lookup", lookup_filter="new", is_question=True, confidence=0.9)
    out = _route("which complaints haven't been picked up yet")
    assert out["intent"] == "lookup"
    assert out["route_slots"]["lookup_filter"] == "new"


def test_llm_unavailable_falls_back_to_rules(monkeypatch):
    monkeypatch.setattr(g, "_llm_route", lambda m, h: (None, {"router_source": "llm_error"}))
    out = _route("start the review of REF-2026-0159")
    assert out["intent"] == "status" and out["route_meta"]["router_source"] == "rules_safe"


# --- grounding -----------------------------------------------------------------


def test_hallucinated_ref_is_dropped(monkeypatch):
    _llm(monkeypatch, intent="lookup", reference_id="REF-2026-9999", confidence=0.9)
    out = _route("how about that one?", history=[{"role": "assistant", "content": "REF-2026-0103 is Closed."}])
    assert out["route_slots"]["reference_id"] is None


def test_history_ref_is_kept(monkeypatch):
    _llm(monkeypatch, intent="lookup", reference_id="REF-2026-0103", confidence=0.9)
    out = _route("how about that one?", history=[{"role": "assistant", "content": "REF-2026-0103 is Closed."}])
    assert out["route_slots"]["reference_id"] == "REF-2026-0103"


def test_invented_notes_are_dropped():
    assert g._grounded_notes("lot verified and photos reviewed", "move it to the approver") is None
    assert g._grounded_notes("everything checks out", "I'm done, everything checks out") == "everything checks out"


# --- confirmation flow ---------------------------------------------------------


def test_yes_runs_the_exact_pending_action(monkeypatch):
    ref = _new_report("confirm yes flow")
    _llm(monkeypatch, intent="status", action="start_review", reference_id=ref, confidence=0.9)
    first = _route(f"I'll pick up {ref} now")
    assert first["intent"] == "clarify"
    pending = first["pending_action_out"]

    # LLM must not even be consulted for the "yes"
    monkeypatch.setattr(g, "_llm_route", lambda m, h: pytest.fail("LLM called for confirmation reply"))
    second = _route("yes", pending=pending)
    assert second["intent"] == "status"
    assert second["forced_args"]["reference_id"] == ref
    out = status_node(second)
    assert ReportService().get(ref)["status"] == "In Review", out.get("response")


def test_no_cancels_without_changes(monkeypatch):
    ref = _new_report("confirm no flow")
    pending = {"intent": "status", "message": f"close {ref}", "forced_args": {"reference_id": ref, "new_status": "In Review"}}
    out = _route("no", pending=pending)
    assert out["intent"] == "clarify" and "cancel" in out["response"].lower()
    assert ReportService().get(ref)["status"] == "New"


def test_other_message_ignores_stale_pending(monkeypatch):
    _llm(monkeypatch, intent="rag", is_question=True, confidence=0.9)
    pending = {"intent": "status", "message": "x", "forced_args": {"reference_id": "REF-2026-0001", "new_status": "Closed"}}
    out = _route("what is the quarantine sop", pending=pending)
    assert out["intent"] == "rag" and out["forced_args"] == {}


def test_confirmation_across_real_chat_turns(monkeypatch):
    """Two real graph turns: pending action survives via message metadata; checkpointer doesn't leak it."""
    from app.modules.agents.graph import LangGraphAgentService

    ref = _new_report("chat-level confirm")
    _llm(monkeypatch, intent="status", action="start_review", reference_id=ref, confidence=0.9)
    monkeypatch.setattr(g, "draft_user_response", lambda **kw: kw.get("fallback") or "")
    svc = LangGraphAgentService()
    sid = svc.chat_svc.create_session("reviewer", title="confirm test")["session_id"]
    r1 = svc.chat(session_id=sid, message=f"I'll pick up {ref} now", actor="reviewer", role="reviewer")
    assert r1["intent"] == "clarify"
    assert ReportService().get(ref)["status"] == "New"
    r2 = svc.chat(session_id=sid, message="yes", actor="reviewer", role="reviewer")
    assert r2["intent"] == "status"
    assert ReportService().get(ref)["status"] == "In Review"
    # A later "yes" must not replay anything (pending was single-use)
    _llm(monkeypatch, intent="direct", confidence=0.9)
    r3 = svc.chat(session_id=sid, message="yes", actor="reviewer", role="reviewer")
    assert r3["intent"] != "status"


# --- infrastructure --------------------------------------------------------------


def test_router_llm_timeout_falls_back(monkeypatch):
    class Slow:
        def generate(self, prompt, system=None):
            time.sleep(2)
            return SimpleNamespace(content='{"intent":"status"}', provider="x", model="y")

    monkeypatch.setattr(g, "get_container", lambda: SimpleNamespace(llm_for=lambda role: Slow()))
    monkeypatch.setattr(g, "get_settings", lambda: SimpleNamespace(
        router_llm_timeout_s=0.3,
        resolve_llm_role=lambda r: {"provider": "x", "model": "y"},
    ))
    t0 = time.perf_counter()
    decision, meta = g._llm_route("hello there", [])
    assert decision is None and meta["router_source"] == "llm_timeout"
    assert time.perf_counter() - t0 < 1.5


def test_parse_route_json_repairs_common_slips():
    d = g._parse_route_json('{"intent":"lookup","reference_id":"REF-2026-0159","confidence":0.98"}')
    assert d and d.intent == "lookup" and d.confidence == 0.98
    assert g._parse_route_json("not json") is None
    assert g._parse_route_json('{"intent":"teleport"}') is None


def test_history_uses_latest_messages():
    from app.services.chat_service import ChatHistoryService

    svc = ChatHistoryService()
    sid = svc.create_session("reviewer", title="history order")["session_id"]
    for i in range(25):
        svc.add_message(session_id=sid, username="reviewer", role="user", content=f"msg {i}")
    msgs = svc.list_messages(sid, "reviewer", limit=20)
    assert [m["content"] for m in msgs][-1] == "msg 24"
    assert msgs[0]["content"] == "msg 5"


# --- regressions found in self-review ---------------------------------------------


def _no_llm(monkeypatch):
    monkeypatch.setattr(g, "_llm_route", lambda m, h: (None, {"router_source": "llm_disabled"}))


_H = [{"role": "user", "content": "REF-2026-0159 details"}, {"role": "assistant", "content": "REF-2026-0159 In Review"}]


def test_rules_fallback_question_never_routes_to_status(monkeypatch):
    _no_llm(monkeypatch)
    assert _route("how to move to the approver", history=_H)["intent"] != "status"


def test_status_node_question_redirects_to_lookup():
    out = status_node(
        {"message": "did the review complete for REF-2026-0159", "actor": "admin", "role": "admin",
         "tool_args": {}, "chat_history": []}
    )
    assert out["details"]["route"] == "lookup"


@pytest.mark.parametrize("reply", ["ok thanks", "never mind", "no thanks", "sounds good", "got it"])
def test_chitchat_is_not_reviewer_notes(reply):
    assert g._looks_like_notes_reply(reply, g._normalize_status_soft(reply)) is False


def test_real_notes_still_accepted():
    m = "seal checked lot verified recommend close"
    assert g._looks_like_notes_reply(m, g._normalize_status_soft(m)) is True


def test_open_cases_is_not_intake():
    assert not g._is_intake_create_request("any open cases")
    assert g._is_intake_create_request("open a case for neurocalm lot-88392")


def test_long_yes_or_no_is_not_a_confirmation():
    assert g._reply_kind("yes and also close ref-2026-0001") is None
    assert g._reply_kind("no close ref-2026-0001 instead") is None
    assert g._reply_kind("yes please") == "yes" and g._reply_kind("no thanks") == "no"


def test_history_ref_write_requires_confirmation(monkeypatch):
    _no_llm(monkeypatch)
    out = _route("move this to the approver", history=_H)
    assert out["intent"] == "clarify"
    assert out["pending_action_out"]["forced_args"]["reference_id"] == "REF-2026-0159"
    # explicit REF still runs directly
    assert _route("start the review of REF-2026-0159")["intent"] == "status"


def test_ambiguous_list_history_never_guesses_ref(monkeypatch):
    _no_llm(monkeypatch)
    lst = [{"role": "assistant", "content": "In review: REF-2026-0150 | REF-2026-0151 | REF-2026-0152"}]
    assert g._ref_from_history(lst) is None
    ref = _new_report("ambiguous close it")
    out = status_node({"message": "close it", "actor": "admin", "role": "admin", "tool_args": {}, "chat_history": lst})
    assert out["details"].get("needs_args") is True
    assert ReportService().get(ref)["status"] == "New"


def test_queue_question_ignores_llm_ref(monkeypatch):
    from app.modules.agents.graph import lookup_node

    out = lookup_node(
        {"message": "list the new cases", "actor": "admin", "role": "admin", "chat_history": _H,
         "route_slots": {"reference_id": "REF-2026-0159", "lookup_filter": None}}
    )
    assert "status_filter" in out["details"]

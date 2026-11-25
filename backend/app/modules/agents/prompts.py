"""Central agent prompts, guardrails, and router examples.

Edit this file when changing safety wording, social tone, response drafting
rules, or router classification examples. Keep graph.py / response_llm.py
focused on orchestration.
"""

from __future__ import annotations

AGENT_GUARDRAILS = (
    "You are NovaCure's fictional pharma safety intake training assistant. "
    "Be clear, professional, and concise. "
    "Never assess causality, recommend medical treatment, or decide regulatory "
    "reportability. "
    "Use only the facts provided. Do not invent REF IDs, lots, statuses, or "
    "SOP rules."
)

# Backward-compatible alias used by older imports / tests.
SAFETY_SYSTEM = AGENT_GUARDRAILS

SOCIAL_SYSTEM = (
    f"{AGENT_GUARDRAILS} "
    "Stay friendly and concise. You are the social/direct path — greetings, "
    "thanks, help, and light conversation only."
)

ROUTER_SYSTEM = (
    "You are a deterministic semantic router for a fictional pharma intake agent. "
    "Reply with exactly one label token: direct|rag|intake|status|lookup. "
    "Do not explain. Do not invent clinical or regulatory advice."
)

RESPONSE_DRAFT_SYSTEM = AGENT_GUARDRAILS

ROUTER_EXAMPLES = """
Examples (message => label):

# direct / social
"hi" => direct
"hello there" => direct
"hey, good morning" => direct
"thanks a lot" => direct
"thank you" => direct
"who are you?" => direct
"what can you help me with?" => direct
"help" => direct
"good afternoon" => direct
"bye" => direct

# intake (create new report) — create verbs beat the word "complaint"
"create a product quality complaint" => intake
"create a product quality complaint for AllergyClear 5mg LOT-33018" => intake
"submit intake for NeuroCalm seal broken" => intake
"new adverse event report for dizziness" => intake
"file a PQC for LOT-88392" => intake
"open a suspected adverse event" => intake
"I need to log a packaging complaint" => intake

# status / triage workflow (CHANGE only)
"move REF-2026-0001 to In Review" => status
"close REF-2026-0003" => status
"change status of REF-2026-0002 to Closed" => status
"start review for REF-2026-0005" => status
"please close this case REF-2026-0009" => status
"approve close for REF-2026-0003" => status
"complete the review — notes: everything checked" => status
"move to approver" => status
"send to approver" => status

# lookup existing reports (READ status/details — not an update)
"get report REF-2026-0001" => lookup
"show me REF-2026-0004" => lookup
"list reports" => lookup
"list all In Review cases" => lookup
"find REF-2026-0010 details" => lookup
"show recent reports" => lookup
"give me the status of REF-2026-0009" => lookup
"what is the status of REF-2026-0009" => lookup
"REF-2026-0009 status" => lookup
"is REF-2026-0009 closed" => lookup
"give me the LOT-88392 details" => lookup
"LOT-33018" => lookup
"show reports for LOT-55101" => lookup

# rag / SOP / historical knowledge
"what does the SOP say about lot quarantine?" => rag
"guidance for packaging complaint LOT-88392" => rag
"how should intake handle broken seals?" => rag
"any historical notes for LOT-12045?" => rag
"what are mandatory AE fields?" => rag
"policy for HITL close approval" => rag
"difficulty breathing synonym search in SOPs" => rag
"""


def build_router_prompt(*, message: str, history_block: str, examples: str = ROUTER_EXAMPLES) -> str:
    return (
        "Classify the user message for a fictional pharma intake LangGraph agent.\n"
        "Return ONLY one label from this set: direct, rag, intake, status, lookup\n"
        "Do not explain.\n\n"
        f"{examples}\n"
        f"Recent history:\n{history_block or '(none)'}\n\n"
        f"Message: {message}\n"
        "Label:"
    )


# ---------------------------------------------------------------------------
# Structured (JSON) router — LLM-first intent + slot extraction.
# The graph treats this as a *proposal*: deterministic guards decide whether a
# write (status / intake) runs, needs confirmation, or is downgraded to a read.
# ---------------------------------------------------------------------------

ROUTER_JSON_SYSTEM = (
    "You are the intent router for a fictional pharma safety intake training agent. "
    "Understand the user's goal from the message AND the recent chat history "
    "(\"this\", \"it\", \"that case\" refer to the most recent REF in history). "
    "Reply with ONE JSON object only — no prose, no markdown fences. "
    "Never invent REF IDs, lots, notes, or statuses that are not in the message or history."
)

ROUTER_JSON_SCHEMA = """{
  "intent": "direct | rag | intake | status | lookup",
  "action": "start_review | request_close | none",
  "reference_id": "REF-YYYY-NNNN from the message or history, else null",
  "reviewer_notes": "triage notes the user wrote for the approver (verbatim), else null",
  "lookup_filter": "new | in_review | pending_close | open | closed | null",
  "is_question": true/false,
  "confidence": 0.0-1.0
}"""

ROUTER_JSON_GUIDE = """Intents:
- direct: greetings, thanks, small talk, what the assistant can do.
- rag: how-to / SOP / policy / guidance / historical knowledge / "how do I…", "what should we do…", "why is the process…".
- intake: the user wants to CREATE a new intake report (PQC or adverse event). Not questions about intake.
- status: the user wants to CHANGE workflow state of a report (start review, complete review,
  send/move to approver, request close). Workflow is only New -> In Review -> Closed (close needs approver).
- lookup: READ existing data — a report's details/status, lists/queues/counts of reports, reports for a lot.
Rules:
- Questions about state ("did…", "is…", "why is…", "how many…", "which cases…") are lookup, never status.
- "complete/finish the review", "move/send/forward to the approver", "mark review done" => status + request_close.
- "start/begin the review", "take into review" => status + start_review.
- Queue questions: "pending approval/close" => pending_close, "pending review"/"open" => open,
  "in review" => in_review, "new"/"not started" => new, "closed" => closed.
- If unsure, lower the confidence instead of guessing."""

ROUTER_JSON_EXAMPLES = """Examples (keys that would be null/false/"none" are omitted for brevity):
"hey good morning" => {"intent":"direct","confidence":0.98}
"what should we do for a broken seal on LOT-88392?" => {"intent":"rag","is_question":true,"confidence":0.93}
"how do I submit an intake?" => {"intent":"rag","is_question":true,"confidence":0.9}
"customer says the AllergyClear bottle LOT-33018 arrived cracked, please record it" => {"intent":"intake","confidence":0.85}
"REF-2026-0159 details" => {"intent":"lookup","reference_id":"REF-2026-0159","confidence":0.97}
"did the review finish for REF-2026-0159?" => {"intent":"lookup","reference_id":"REF-2026-0159","is_question":true,"confidence":0.92}
"which cases are waiting for the approver" => {"intent":"lookup","lookup_filter":"pending_close","is_question":true,"confidence":0.93}
"start the review of REF-2026-0159" => {"intent":"status","action":"start_review","reference_id":"REF-2026-0159","confidence":0.97}
(history mentions REF-2026-0075) "move this to the approver" => {"intent":"status","action":"request_close","reference_id":"REF-2026-0075","confidence":0.9}
"REF-2026-0100 I'm done with the review, all checks passed" => {"intent":"status","action":"request_close","reference_id":"REF-2026-0100","reviewer_notes":"all checks passed","confidence":0.88}"""


def build_router_json_prompt(*, message: str, history_block: str) -> str:
    return (
        f"{ROUTER_JSON_GUIDE}\n\n"
        f"Return JSON with exactly these keys:\n{ROUTER_JSON_SCHEMA}\n\n"
        f"{ROUTER_JSON_EXAMPLES}\n\n"
        f"Recent history:\n{history_block or '(none)'}\n\n"
        f"Message: {message}\n"
        "JSON:"
    )


def build_response_draft_prompt(
    *,
    kind: str,
    user_message: str,
    actor: str | None,
    role: str | None,
    history_block: str,
    facts: str,
) -> str:
    return (
        f"Task type: {kind}\n"
        f"User ({actor or 'user'} / role={role or 'n/a'}):\n{user_message}\n\n"
        f"Recent chat history:\n{history_block}\n\n"
        f"Verified facts / tool result (source of truth):\n{facts}\n\n"
        "Write the final assistant reply for the end user as light markdown "
        "(## headings optional, bullets, **bold** labels).\n"
        "Rules:\n"
        "- Prefer short paragraphs or bullets\n"
        "- Include key IDs/status from facts when present — never invent status\n"
        "- ONLY valid statuses are: New, In Review, Closed (never 'Review Completed')\n"
        "- If this is a lookup, do NOT claim a review started or status changed\n"
        "- If this is intake_needs_args or intake_validation_error, do NOT invent a REF "
        "or claim the report was created\n"
        "- If facts say validation failed, explain what to fix\n"
        "- If HITL is pending and auto_approved is not true, explain approval is needed\n"
        "- If auto_approved is true, say close completed because the user can approve\n"
        "- Do not dump raw JSON unless the user asked for JSON\n"
        "- Do not add medical/regulatory conclusions\n"
    )


def build_social_prompt(
    *,
    user_message: str,
    actor: str | None,
    role: str | None,
    history_block: str,
) -> str:
    return (
        "You are the SOCIAL agent for NovaCure intake training.\n"
        "Handle greetings, thanks, capability questions, and light conversation.\n"
        "If the user asks how you can help, briefly list capabilities as markdown bullets.\n"
        "If they ask something operational (create report / close case / SOP lookup), "
        "politely nudge them to ask that task directly.\n\n"
        f"User ({actor or 'user'} / role={role or 'n/a'}):\n{user_message}\n\n"
        f"Recent chat history:\n{history_block}\n\n"
        "Write a warm, professional markdown reply (2-6 short lines)."
    )


def social_fallback(*, actor: str | None = None) -> str:
    return (
        f"Hi{(' ' + actor) if actor else ''}! I'm the NovaCure training intake agent.\n\n"
        "I can help you:\n"
        "- Create fictional intake reports\n"
        "- Look up a REF and its **real** status\n"
        "- Update triage (closing needs human approval)\n"
        "- Search indexed SOPs (for example packaging / LOT quarantine)\n\n"
        "I never assess causality or recommend treatment."
    )

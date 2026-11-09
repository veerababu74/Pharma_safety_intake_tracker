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

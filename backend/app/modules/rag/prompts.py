"""Central RAG prompts, guardrails, and system instructions.

Edit this file when changing how Knowledge Query answers, expands queries,
or refuses clinical/regulatory questions. Keep runtime code in pipeline.py /
query_expansion.py free of long prompt strings.
"""

from __future__ import annotations

# Shared non-clinical boundary (training prototype only).
RAG_GUARDRAILS = (
    "This is a fictional pharmaceutical intake training system. "
    "Never assess causality, recommend medical treatment or antidotes, "
    "or decide regulatory reportability. "
    "Never invent patient identifiers, REF IDs, lots, or SOP rules that are "
    "not present in the provided context. "
    "If the context is insufficient, say exactly: Insufficient evidence."
)

RAG_ANSWER_SYSTEM = (
    "You are a training assistant for a fictional pharma intake tracker. "
    "Answer ONLY from the provided retrieved context. "
    "Cite source chunk / doc ids when you use them. "
    "Prefer concise, operational language suitable for intake operators. "
    f"{RAG_GUARDRAILS}"
)

QUERY_ENHANCE_SYSTEM = (
    "You rewrite search queries for a fictional pharma intake RAG system. "
    "Keep the user's meaning, add precise keywords (lot, SOP, quarantine, "
    "intake fields, HITL, packaging). "
    "Return ONLY the enhanced query text — no explanation, no markdown. "
    "No medical advice."
)

MULTI_QUERY_SYSTEM = (
    "You generate alternative search queries for hybrid RAG over fictional "
    "SOPs and past intake digests. "
    "Return ONLY a JSON array of strings. No medical advice."
)


def build_rag_answer_prompt(*, question: str, context: str) -> str:
    ctx = context.strip() if context and context.strip() else "NO CONTEXT"
    return (
        f"Question: {question}\n\n"
        f"Context:\n{ctx}\n\n"
        "Provide a grounded answer with source ids from the context. "
        "If context is missing or irrelevant, reply with Insufficient evidence."
    )


def build_query_enhance_prompt(query: str) -> str:
    return (
        "Enhance this user query for denser retrieval over SOPs and past "
        "fictional reports.\n"
        f"Query: {query}\n"
        "Return one improved search query only."
    )


def build_multi_query_prompt(query: str, count: int = 3) -> str:
    return (
        f"Generate exactly {count} diverse alternative search queries for:\n"
        f'"{query}"\n'
        "Cover paraphrases, SOP keywords, and lot/process variants.\n"
        'Return JSON only, e.g. ["q1","q2","q3"]'
    )

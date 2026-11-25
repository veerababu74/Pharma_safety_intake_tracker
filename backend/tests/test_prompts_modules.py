from app.modules.agents import prompts as agent_prompts
from app.modules.rag import prompts as rag_prompts


def test_rag_prompts_include_guardrails():
    assert "Insufficient evidence" in rag_prompts.RAG_GUARDRAILS
    assert "causality" in rag_prompts.RAG_ANSWER_SYSTEM.lower()
    prompt = rag_prompts.build_rag_answer_prompt(question="LOT-88392 quarantine?", context="")
    assert "LOT-88392" in prompt
    assert "Insufficient evidence" in prompt
    assert rag_prompts.build_query_enhance_prompt("seal broken").startswith("Enhance")
    assert "JSON" in rag_prompts.build_multi_query_prompt("HITL", count=3)


def test_agent_prompts_include_guardrails_and_builders():
    assert "causality" in agent_prompts.AGENT_GUARDRAILS.lower()
    assert "direct|rag|intake|status|lookup" in agent_prompts.ROUTER_SYSTEM
    assert "LOT-88392" in agent_prompts.ROUTER_EXAMPLES
    router = agent_prompts.build_router_prompt(message="hello", history_block="(none)")
    assert "Label:" in router
    draft = agent_prompts.build_response_draft_prompt(
        kind="lookup",
        user_message="show REF-2026-0001",
        actor="reviewer",
        role="reviewer",
        history_block="(none)",
        facts='{"ok": true}',
    )
    assert "New, In Review, Closed" in draft
    social = agent_prompts.build_social_prompt(
        user_message="hi",
        actor="operator",
        role="operator",
        history_block="(none)",
    )
    assert "SOCIAL agent" in social
    assert "never assess causality" in agent_prompts.social_fallback(actor="Maya").lower()

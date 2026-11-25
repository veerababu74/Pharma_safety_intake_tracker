from evaluation.dataset import load_agent_gold, load_rag_gold

RAG_INTENTS = {"report_lookup", "lot_crosswalk", "sop_rule", "colloquial", "refusal"}
AGENT_INTENTS = {"direct", "rag", "intake", "status", "lookup"}


def test_rag_gold_has_thirty_grounded_questions():
    rows = load_rag_gold()
    assert len(rows) >= 30
    ids = [row["id"] for row in rows]
    assert len(ids) == len(set(ids))
    assert sum(1 for row in rows if row["should_refuse"]) >= 2
    for row in rows:
        assert row["question"] and row["reference_answer"]
        assert row["category"] in RAG_INTENTS
        assert row["must_contain"]


def test_agent_gold_covers_router_and_guardrails():
    rows = load_agent_gold()
    assert len(rows) >= 30
    ids = [row["id"] for row in rows]
    assert len(ids) == len(set(ids))
    intents = {row["expected_intent"] for row in rows}
    assert AGENT_INTENTS <= intents
    assert any(row["expects_hitl"] for row in rows)
    assert any(row["expects_validation_error"] for row in rows)
    for row in rows:
        assert row["utterance"]
        assert row["expected_intent"] in AGENT_INTENTS
        if row["expected_tool"] is None:
            assert row["expected_intent"] == "direct"

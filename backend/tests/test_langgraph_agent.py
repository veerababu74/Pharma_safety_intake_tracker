from app.modules.agents.graph import ROUTER_EXAMPLES, _extract_route_label, _rule_route, build_agent_graph


def test_rule_router_intents():
    assert _rule_route("hello") == "direct"
    assert _rule_route("thanks a lot") == "direct"
    assert _rule_route("create a complaint for LOT-88392") == "intake"
    assert _rule_route("close REF-2026-0001") == "status"
    assert _rule_route("quarantine SOP for packaging") == "rag"
    assert _rule_route("get report REF-2026-0001") == "lookup"
    assert _rule_route("what can you help me with?") == "direct"
    assert _rule_route("hi, what can you help me with?") == "direct"


def test_router_examples_cover_all_labels():
    for label in ("direct", "rag", "intake", "status", "lookup"):
        assert f"=> {label}" in ROUTER_EXAMPLES


def test_extract_route_label():
    assert _extract_route_label("intake") == "intake"
    assert _extract_route_label("Label: status") == "status"
    assert _extract_route_label("rag") == "rag"


def test_graph_compiles_with_checkpointer():
    graph = build_agent_graph()
    assert graph is not None

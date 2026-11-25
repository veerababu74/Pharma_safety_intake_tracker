from app.modules.agents.orchestrator import AgentOrchestrator


def test_circuit_breaker_trips_on_repeated_invalid_args():
    agent = AgentOrchestrator()
    bad = {"report_type": "Product Quality Complaint", "product_name": "X", "batch_lot_number": "ABC"}
    r1 = agent.handle("create complaint", actor="operator", role="operator", tool_args=bad)
    r2 = agent.handle("create complaint", actor="operator", role="operator", tool_args=bad)
    r3 = agent.handle("create complaint", actor="operator", role="operator", tool_args=bad)
    assert r1.get("error") == "validation_failed"
    assert r2.get("error") == "validation_failed"
    assert r3.get("halted") is True

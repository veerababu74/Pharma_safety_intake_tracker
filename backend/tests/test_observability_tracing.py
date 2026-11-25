"""Production-style RAG + agent tracing into custom SQLite."""

from app.core.container import get_container
from app.db.models.obs import TraceEvent
from app.db.session import DatabaseKind, db_manager
from app.modules.tracing.base import safe_preview
from app.modules.tracing.custom_tracer import CustomSQLiteTracer


def setup_module():
    db_manager.init()


def test_safe_preview_truncates():
    text = safe_preview("x" * 5000, limit=100)
    assert len(text) <= 100
    assert text.endswith("...")


def test_custom_tracer_persists_mutated_metadata():
    tracer = CustomSQLiteTracer()
    with tracer.span(
        "unit_test_span",
        kind="span",
        actor="tester",
        role="admin",
        input_preview="hello",
        metadata={"flow": "test"},
    ) as span:
        span.set_output({"ok": True})
        span.update(llm_model="mock-1", custom_flag=True)
        tid = span.trace_id

    with db_manager.session(DatabaseKind.OBS) as session:
        row = (
            session.query(TraceEvent)
            .filter(TraceEvent.trace_id == tid, TraceEvent.name == "unit_test_span")
            .order_by(TraceEvent.id.desc())
            .first()
        )
        assert row is not None
        assert row.input_preview == "hello"
        assert "ok" in (row.output_preview or "")
        assert "custom_flag" in (row.metadata_json or "")
        assert "llm_model" in (row.metadata_json or "")
        assert row.latency_ms is not None


def test_nested_spans_share_trace_id():
    tracer = CustomSQLiteTracer()
    with tracer.span("parent_span", kind="span", metadata={"flow": "test"}) as parent:
        with tracer.span("child_span", kind="tool", parent=parent, metadata={"flow": "test"}) as child:
            assert child.trace_id == parent.trace_id
            assert child.parent_span_id == parent.span_id
            child.set_output("child-out")
            tid = parent.trace_id

    with db_manager.session(DatabaseKind.OBS) as session:
        rows = session.query(TraceEvent).filter(TraceEvent.trace_id == tid).all()
        names = {r.name for r in rows}
        assert "parent_span" in names
        assert "child_span" in names


def test_rag_query_writes_trace_tree():
    container = get_container()
    result = container.rag.query("What is intake mandatory fields?", actor="tester", role="admin", top_n=3)
    assert "answer" in result
    # Root span should exist with retrieval children
    with db_manager.session(DatabaseKind.OBS) as session:
        rows = (
            session.query(TraceEvent)
            .filter(TraceEvent.name == "hybrid_rag_query")
            .order_by(TraceEvent.id.desc())
            .limit(1)
            .all()
        )
        assert rows
        tid = rows[0].trace_id
        tree = session.query(TraceEvent).filter(TraceEvent.trace_id == tid).all()
        names = {r.name for r in tree}
        assert "query_expansion" in names
        assert "hybrid_retrieval" in names
        assert "rerank" in names
        assert "rag_llm_generation" in names
        gen = next(r for r in tree if r.name == "rag_llm_generation")
        assert gen.kind == "generation"
        assert gen.output_preview

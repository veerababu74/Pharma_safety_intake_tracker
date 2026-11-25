from app.api.routes.observability import _token_totals, _tokens_by_span
from app.core.container import get_container
from app.db.models.obs import TraceEvent
from app.db.session import DatabaseKind, db_manager
from app.modules.llms.providers import MockLLMProvider
from app.modules.llms.usage import estimate_tokens, with_estimated_tokens
from app.modules.tracing.base import SpanContext
from app.modules.tracing.custom_tracer import CustomSQLiteTracer


def setup_module():
    db_manager.init()
    get_container.cache_clear()


def test_estimate_and_pack_tokens():
    assert estimate_tokens("abcd") == 1
    prompt, completion, total = with_estimated_tokens(
        prompt="hello world",
        system="sys",
        content="answer text here",
        prompt_tokens=None,
        completion_tokens=None,
        total_tokens=None,
    )
    assert prompt > 0 and completion > 0 and total == prompt + completion


def test_mock_llm_returns_token_counts():
    resp = MockLLMProvider().generate("packaging LOT-88392", system="safety")
    assert resp.input_tokens and resp.input_tokens > 0
    assert resp.output_tokens and resp.output_tokens > 0
    assert resp.total_tokens == resp.input_tokens + resp.output_tokens


def test_span_record_tokens_and_persist():
    tracer = CustomSQLiteTracer()
    with tracer.span("tok_parent", kind="span", metadata={"flow": "test"}) as parent:
        with tracer.span("tok_child", kind="generation", parent=parent, metadata={"flow": "test"}) as child:
            child.record_tokens(prompt_tokens=11, completion_tokens=7, bubble=False, llm_role="router")
            tid = parent.trace_id

    with db_manager.session(DatabaseKind.OBS) as session:
        child_row = (
            session.query(TraceEvent)
            .filter(TraceEvent.trace_id == tid, TraceEvent.name == "tok_child")
            .one()
        )
        assert child_row.prompt_tokens == 11
        assert child_row.completion_tokens == 7
        assert child_row.token_usage == 18


def test_instrumented_llm_writes_tokens_on_active_span():
    get_container.cache_clear()
    container = get_container()
    tracer = container.tracer
    llm = container.llm_for("rag")
    with tracer.span(
        "rag_llm_generation_test",
        kind="generation",
        actor="tester",
        role="admin",
        metadata={"flow": "test", "llm_role": "rag"},
    ) as span:
        resp = llm.generate("What is quarantine timing for LOT-88392?", system="Be brief.")
        tid = span.trace_id
    assert resp.total_tokens and resp.total_tokens > 0

    with db_manager.session(DatabaseKind.OBS) as session:
        row = (
            session.query(TraceEvent)
            .filter(TraceEvent.trace_id == tid, TraceEvent.name == "rag_llm_generation_test")
            .one()
        )
        assert row.prompt_tokens and row.prompt_tokens > 0
        assert row.completion_tokens and row.completion_tokens > 0
        assert row.token_usage == row.prompt_tokens + row.completion_tokens


def test_token_aggregation_helpers():
    spans = [
        {
            "span_id": "a",
            "name": "agent_router",
            "kind": "generation",
            "prompt_tokens": 10,
            "completion_tokens": 2,
            "token_usage": 12,
            "metadata": {"llm_role": "router"},
        },
        {
            "span_id": "b",
            "name": "agent_social",
            "kind": "generation",
            "prompt_tokens": 20,
            "completion_tokens": 8,
            "token_usage": 28,
            "metadata": {"llm_role": "social"},
        },
        {"span_id": "c", "name": "tool", "kind": "tool", "metadata": {}},
    ]
    totals = _token_totals(spans)
    assert totals == {"prompt_tokens": 30, "completion_tokens": 10, "token_usage": 40}
    by_span = _tokens_by_span(spans)
    assert len(by_span) == 2
    assert by_span[0]["name"] == "agent_social"


def test_parent_ctx_link():
    parent = SpanContext(trace_id="t", span_id="p", name="parent")
    child = SpanContext(trace_id="t", span_id="c", parent_span_id="p", name="child", parent_ctx=parent)
    child.record_tokens(prompt_tokens=5, completion_tokens=1, bubble=True)
    assert child.metadata["token_usage"] == 6
    assert parent.metadata["token_usage"] == 6

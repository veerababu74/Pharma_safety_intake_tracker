import { useEffect, useMemo, useState } from 'react';
import { apiRequest } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { TraceFlowDiagram, spanTimeline } from '../components/TraceFlowDiagram';
import { useToast } from '../components/Toast';
import { Button, Card, PageHeader, Pagination, Select, Table } from '../components/ui';
import { usePagination } from '../hooks/usePagination';

type TraceSummary = {
  trace_id: string;
  name: string;
  flow?: string;
  status: string;
  actor?: string;
  span_count: number;
  latency_ms?: number;
  input_preview?: string;
  intent?: string;
  llm_model?: string;
  llm_provider?: string;
  prompt_tokens?: number;
  completion_tokens?: number;
  token_usage?: number;
  created_at?: string;
};

type TokenBySpan = {
  span_id?: string;
  name?: string;
  kind?: string;
  step?: string;
  llm_role?: string;
  llm_provider?: string;
  llm_model?: string;
  prompt_tokens: number;
  completion_tokens: number;
  token_usage: number;
};

type TraceDetail = {
  trace_id: string;
  root: any;
  span_count: number;
  spans: any[];
  tree: any[];
  prompt_tokens?: number;
  completion_tokens?: number;
  token_usage?: number;
  tokens_by_span?: TokenBySpan[];
};

function formatTokens(value?: number | null): string {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return Number(value).toLocaleString();
}

type DetailTab = 'flow' | 'text' | 'timeline';

function SpanTree({
  nodes,
  depth = 0,
  focusId,
}: {
  nodes: any[];
  depth?: number;
  focusId?: string | null;
}) {
  if (!nodes?.length) return null;
  return (
    <ul className="span-tree" style={{ marginLeft: depth ? 16 : 0 }}>
      {nodes.map((n) => (
        <li key={n.span_id} className={focusId === n.span_id ? 'span-focus' : undefined} id={`span-${n.span_id}`}>
          <div className="span-row">
            <strong>{n.name}</strong>
            <span className={`span-kind kind-${(n.kind || 'span').toLowerCase()}`}>{n.kind}</span>
            <span className={`badge ${n.status === 'error' ? 'badge-pending' : 'badge-closed'}`}>{n.status}</span>
            <span className="muted"> · {(n.latency_ms ?? 0).toFixed?.(1) ?? n.latency_ms} ms</span>
            {n.token_usage || n.prompt_tokens || n.completion_tokens ? (
              <span className="muted">
                {' '}
                · tokens in {formatTokens(n.prompt_tokens)} / out {formatTokens(n.completion_tokens)} / total{' '}
                {formatTokens(n.token_usage ?? (Number(n.prompt_tokens || 0) + Number(n.completion_tokens || 0)))}
              </span>
            ) : null}
          </div>
          {n.input_preview ? (
            <div className="muted small">in: {String(n.input_preview).slice(0, 220)}</div>
          ) : null}
          {n.output_preview ? (
            <div className="muted small">out: {String(n.output_preview).slice(0, 280)}</div>
          ) : null}
          {n.metadata && Object.keys(n.metadata).length ? (
            <pre className="pre compact">{JSON.stringify(n.metadata, null, 2)}</pre>
          ) : null}
          <SpanTree nodes={n.children || []} depth={depth + 1} focusId={focusId} />
        </li>
      ))}
    </ul>
  );
}

function StatusChip({ status }: { status: string }) {
  const cls =
    status === 'error' ? 'badge-pending' : status === 'ok' ? 'badge-closed' : 'badge-new';
  return <span className={`badge ${cls}`}>{status}</span>;
}

export function ObservabilityPage() {
  const { user } = useAuth();
  const toast = useToast();
  const [config, setConfig] = useState<any>(null);
  const [traces, setTraces] = useState<TraceSummary[]>([]);
  const [selected, setSelected] = useState<TraceDetail | null>(null);
  const [flow, setFlow] = useState('');
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState<DetailTab>('flow');
  const [focusSpanId, setFocusSpanId] = useState<string | null>(null);
  const [showConfig, setShowConfig] = useState(false);
  const pager = usePagination(traces, 10);

  const timeline = useMemo(
    () => (selected ? spanTimeline(selected.tree || []) : []),
    [selected],
  );

  const load = async (flowFilter = flow) => {
    setLoading(true);
    try {
      const q = flowFilter ? `?limit=200&flow=${encodeURIComponent(flowFilter)}` : '?limit=200';
      const [cfg, list] = await Promise.all([
        apiRequest('/observability/config', {}, user?.access_token),
        apiRequest<TraceSummary[]>(`/observability/traces${q}`, {}, user?.access_token),
      ]);
      setConfig(cfg);
      setTraces(list);
      pager.setPage(1);
    } catch (e: any) {
      toast.error('Could not load traces', e.message || 'Please try again');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!user?.access_token) return;
    load();
  }, [user?.access_token]);

  const openTrace = async (traceId: string) => {
    setFocusSpanId(null);
    setTab('flow');
    try {
      const detail = await apiRequest<TraceDetail>(
        `/observability/traces/${traceId}`,
        {},
        user?.access_token,
      );
      setSelected(detail);
    } catch (e: any) {
      toast.error('Could not open trace', e.message || 'Please try again');
    }
  };

  const jumpToTextSpan = (span: any) => {
    setFocusSpanId(span.span_id);
    setTab('text');
    requestAnimationFrame(() => {
      document.getElementById(`span-${span.span_id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  };

  const stats = useMemo(() => {
    const agent = traces.filter((t) => t.flow === 'agent').length;
    const rag = traces.filter((t) => t.flow === 'rag').length;
    const errors = traces.filter((t) => t.status === 'error').length;
    const prompt = traces.reduce((sum, t) => sum + Number(t.prompt_tokens || 0), 0);
    const completion = traces.reduce((sum, t) => sum + Number(t.completion_tokens || 0), 0);
    const tokens = traces.reduce((sum, t) => sum + Number(t.token_usage || 0), 0);
    return { total: traces.length, agent, rag, errors, prompt, completion, tokens };
  }, [traces]);

  return (
    <div className="obs-page">
      <PageHeader
        title="Monitoring & Tracing"
        subtitle="Inspect RAG and LangGraph agent runs as a flow diagram or detailed text trace."
      />
      <div className="stats-row obs-stats">
        <div className="stat-card">
          <span className="label">Traces loaded</span>
          <span className="value">{stats.total}</span>
        </div>
        <div className="stat-card">
          <span className="label">Agent flows</span>
          <span className="value">{stats.agent}</span>
        </div>
        <div className="stat-card">
          <span className="label">RAG flows</span>
          <span className="value">{stats.rag}</span>
        </div>
        <div className="stat-card">
          <span className="label">Errors</span>
          <span className="value">{stats.errors}</span>
        </div>
        <div className="stat-card">
          <span className="label">Input tokens</span>
          <span className="value">{formatTokens(stats.prompt)}</span>
        </div>
        <div className="stat-card">
          <span className="label">Output tokens</span>
          <span className="value">{formatTokens(stats.completion)}</span>
        </div>
        <div className="stat-card">
          <span className="label">Total tokens</span>
          <span className="value">{formatTokens(stats.tokens)}</span>
        </div>
      </div>

      <Card
        title="Tracing configuration"
        actions={
          <div className="row-actions">
            <Button variant="ghost" onClick={() => setShowConfig((v) => !v)}>
              {showConfig ? 'Hide' : 'Show'}
            </Button>
            <Button variant="ghost" onClick={() => load()} disabled={loading}>
              {loading ? 'Refreshing…' : 'Refresh'}
            </Button>
          </div>
        }
      >
        {showConfig ? (
          <pre className="pre">{JSON.stringify(config, null, 2)}</pre>
        ) : (
          <p className="muted" style={{ margin: 0 }}>
            Mode: <strong>{config?.tracing_mode || '—'}</strong>
            {config?.langfuse_configured ? ' · Langfuse connected' : ' · Custom SQLite'}
            {' · '}
            Click a trace row to open the Mermaid-style execution flow.
          </p>
        )}
      </Card>

      <Card
        title="Traces"
        actions={
          <div className="obs-filters">
            <Select
              value={flow}
              onChange={(e) => {
                const v = e.target.value;
                setFlow(v);
                load(v);
              }}
            >
              <option value="">All flows</option>
              <option value="rag">RAG</option>
              <option value="agent">Agent</option>
            </Select>
          </div>
        }
      >
        <Table
          headers={[
            'Time',
            'Name',
            'Flow',
            'Intent',
            'Status',
            'Actor',
            'Spans',
            'Latency',
            'In / Out / Total',
            'Model',
          ]}
          rows={pager.pageItems.map((t) => [
            <button key={t.trace_id} className="linkish" onClick={() => openTrace(t.trace_id)}>
              {t.created_at || '—'}
            </button>,
            <button key={`${t.trace_id}-name`} className="linkish" onClick={() => openTrace(t.trace_id)}>
              {t.name}
            </button>,
            <span key={`${t.trace_id}-flow`} className={`flow-chip flow-${t.flow || 'other'}`}>
              {t.flow || '—'}
            </span>,
            t.intent || '—',
            <StatusChip key={`${t.trace_id}-st`} status={t.status} />,
            t.actor || '—',
            t.span_count,
            t.latency_ms?.toFixed?.(1) ?? '—',
            <span key={`${t.trace_id}-tok`} className="token-cell">
              {formatTokens(t.prompt_tokens)} / {formatTokens(t.completion_tokens)} / {formatTokens(t.token_usage)}
            </span>,
            t.llm_model ? `${t.llm_provider || ''}:${t.llm_model}` : '—',
          ])}
        />
        <Pagination
          page={pager.page}
          totalPages={pager.totalPages}
          total={pager.total}
          from={pager.from}
          to={pager.to}
          pageSize={pager.pageSize}
          onPageChange={pager.setPage}
          onPageSizeChange={pager.setPageSize}
        />
      </Card>

      {selected ? (
        <Card
          title={`Trace ${selected.trace_id}`}
          actions={
            <Button variant="ghost" onClick={() => setSelected(null)}>
              Close
            </Button>
          }
        >
          <div className="trace-summary">
            <div>
              <span className="muted">Root</span>
              <strong>{selected.root?.name || '—'}</strong>
            </div>
            <div>
              <span className="muted">Spans</span>
              <strong>{selected.span_count}</strong>
            </div>
            <div>
              <span className="muted">Status</span>
              <StatusChip status={selected.root?.status || 'ok'} />
            </div>
            <div>
              <span className="muted">Latency</span>
              <strong>{(selected.root?.latency_ms ?? 0).toFixed?.(1) ?? '—'} ms</strong>
            </div>
            <div>
              <span className="muted">Input tokens</span>
              <strong>{formatTokens(selected.prompt_tokens)}</strong>
            </div>
            <div>
              <span className="muted">Output tokens</span>
              <strong>{formatTokens(selected.completion_tokens)}</strong>
            </div>
            <div>
              <span className="muted">Total tokens</span>
              <strong>{formatTokens(selected.token_usage)}</strong>
            </div>
            {selected.root?.metadata?.intent ? (
              <div>
                <span className="muted">Intent</span>
                <strong>{String(selected.root.metadata.intent)}</strong>
              </div>
            ) : null}
            {selected.root?.metadata?.flow ? (
              <div>
                <span className="muted">Flow</span>
                <span className={`flow-chip flow-${selected.root.metadata.flow}`}>
                  {String(selected.root.metadata.flow)}
                </span>
              </div>
            ) : null}
          </div>

          {selected.tokens_by_span && selected.tokens_by_span.length > 0 ? (
            <div className="token-breakdown">
              <h3>Tokens by agent / span</h3>
              <Table
                headers={['Span', 'Role', 'Provider', 'Input', 'Output', 'Total']}
                rows={selected.tokens_by_span.map((row) => [
                  <button
                    key={row.span_id || row.name}
                    type="button"
                    className="linkish"
                    onClick={() => row.span_id && jumpToTextSpan({ span_id: row.span_id })}
                  >
                    {row.name || '—'}
                    {row.step ? ` · ${row.step}` : ''}
                  </button>,
                  row.llm_role || row.kind || '—',
                  row.llm_model ? `${row.llm_provider || ''}:${row.llm_model}` : row.llm_provider || '—',
                  formatTokens(row.prompt_tokens),
                  formatTokens(row.completion_tokens),
                  formatTokens(row.token_usage),
                ])}
              />
            </div>
          ) : (
            <p className="muted">No token usage recorded on this trace yet. Run an Agent or RAG query after restarting the API.</p>
          )}

          {(selected.root?.input_preview || selected.root?.output_preview) && (
            <div className="trace-io">
              {selected.root.input_preview ? (
                <div>
                  <h3>Input</h3>
                  <pre className="pre compact">{String(selected.root.input_preview)}</pre>
                </div>
              ) : null}
              {selected.root.output_preview ? (
                <div>
                  <h3>Output</h3>
                  <pre className="pre compact">{String(selected.root.output_preview)}</pre>
                </div>
              ) : null}
            </div>
          )}

          <div className="trace-tabs" role="tablist" aria-label="Trace views">
            <button
              type="button"
              role="tab"
              className={tab === 'flow' ? 'active' : ''}
              aria-selected={tab === 'flow'}
              onClick={() => setTab('flow')}
            >
              Flow diagram
            </button>
            <button
              type="button"
              role="tab"
              className={tab === 'text' ? 'active' : ''}
              aria-selected={tab === 'text'}
              onClick={() => setTab('text')}
            >
              Text tree
            </button>
            <button
              type="button"
              role="tab"
              className={tab === 'timeline' ? 'active' : ''}
              aria-selected={tab === 'timeline'}
              onClick={() => setTab('timeline')}
            >
              Timeline
            </button>
          </div>

          {tab === 'flow' ? (
            <TraceFlowDiagram tree={selected.tree || []} onSelectSpan={jumpToTextSpan} />
          ) : null}

          {tab === 'text' ? (
            <div className="scroll-panel trace-text-panel">
              <SpanTree nodes={selected.tree} focusId={focusSpanId} />
            </div>
          ) : null}

          {tab === 'timeline' ? (
            <div className="trace-timeline">
              {timeline.map((s, idx) => (
                <button
                  type="button"
                  key={s.span_id}
                  className="trace-timeline-item"
                  onClick={() => jumpToTextSpan(s)}
                >
                  <span className="trace-timeline-index">{idx + 1}</span>
                  <div className="trace-timeline-body">
                    <strong>{s.name}</strong>
                    <span className="muted">
                      {s.kind} · {s.status} · {(s.latency_ms ?? 0).toFixed?.(1) ?? s.latency_ms} ms
                      {s.token_usage || s.prompt_tokens || s.completion_tokens
                        ? ` · in ${formatTokens(s.prompt_tokens)} / out ${formatTokens(s.completion_tokens)} / total ${formatTokens(s.token_usage)}`
                        : ''}
                    </span>
                    {s.input_preview ? (
                      <span className="muted small">in: {String(s.input_preview).slice(0, 140)}</span>
                    ) : null}
                    {s.output_preview ? (
                      <span className="muted small">out: {String(s.output_preview).slice(0, 160)}</span>
                    ) : null}
                  </div>
                </button>
              ))}
              {!timeline.length ? <p className="muted">No spans.</p> : null}
            </div>
          ) : null}
        </Card>
      ) : null}
    </div>
  );
}

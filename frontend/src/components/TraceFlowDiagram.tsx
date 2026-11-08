import { useEffect, useId, useMemo, useRef, useState } from 'react';
import mermaid from 'mermaid';

type SpanNode = {
  span_id: string;
  name?: string;
  kind?: string;
  status?: string;
  latency_ms?: number;
  input_preview?: string;
  output_preview?: string;
  prompt_tokens?: number;
  completion_tokens?: number;
  token_usage?: number;
  metadata?: Record<string, unknown>;
  children?: SpanNode[];
};

mermaid.initialize({
  startOnLoad: false,
  securityLevel: 'loose',
  theme: 'base',
  flowchart: {
    curve: 'basis',
    htmlLabels: true,
    padding: 12,
    nodeSpacing: 36,
    rankSpacing: 48,
  },
  themeVariables: {
    fontFamily: '"Source Sans 3", "Segoe UI", sans-serif',
    fontSize: '13px',
    primaryColor: '#e7f3ff',
    primaryTextColor: '#1c1e21',
    primaryBorderColor: '#1877f2',
    lineColor: '#65676b',
    secondaryColor: '#f7f8fa',
    tertiaryColor: '#fff6db',
  },
});

function esc(text: string): string {
  return text
    .replace(/\\/g, '/')
    .replace(/"/g, "'")
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/[\[\]{}|#]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function short(text: unknown, max = 72): string {
  const s = esc(String(text ?? ''));
  if (!s) return '';
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

function kindClass(kind?: string, name?: string): string {
  const k = (kind || '').toLowerCase();
  const n = (name || '').toLowerCase();
  if (k === 'tool' || n.includes('tool') || n.startsWith('status_') || n.startsWith('intake_') || n.startsWith('lookup_')) {
    return 'tool';
  }
  if (k === 'generation' || n.includes('llm') || n.includes('route') || n.includes('response')) {
    return 'llm';
  }
  if (k === 'rag' || n.includes('rag') || n.includes('retriev') || n.includes('embed')) {
    return 'rag';
  }
  if ((name || '').toLowerCase().includes('hitl') || n.includes('interrupt')) {
    return 'hitl';
  }
  return 'span';
}

function nodeShape(id: string, label: string, cls: string): string {
  const body = `"${label}"`;
  if (cls === 'tool') return `${id}[${body}]`;
  if (cls === 'llm') return `${id}{{${body}}}`;
  if (cls === 'rag') return `${id}([${body}])`;
  if (cls === 'hitl') return `${id}((${body}))`;
  return `${id}(${body})`;
}

function buildMermaid(tree: SpanNode[]): string {
  const lines: string[] = [
    'flowchart TD',
    '  classDef span fill:#ffffff,stroke:#ced0d4,color:#1c1e21,stroke-width:1.5px',
    '  classDef tool fill:#e7f3ff,stroke:#1877f2,color:#0b5ed7,stroke-width:1.8px',
    '  classDef llm fill:#fff6db,stroke:#f7b928,color:#8a6a00,stroke-width:1.8px',
    '  classDef rag fill:#e7f6eb,stroke:#31a24c,color:#1b7a32,stroke-width:1.8px',
    '  classDef hitl fill:#ffe6ea,stroke:#e41e3f,color:#b00020,stroke-width:1.8px',
    '  classDef error fill:#ffe6ea,stroke:#e41e3f,color:#b00020,stroke-width:2px',
  ];

  let counter = 0;
  const walk = (node: SpanNode, parentId?: string) => {
    const id = `N${counter++}`;
    const meta = node.metadata || {};
    const intent = meta.intent ? ` · ${short(meta.intent, 28)}` : '';
    const tool = meta.tool_name ? ` · ${short(meta.tool_name, 28)}` : '';
    const latency =
      node.latency_ms != null && !Number.isNaN(Number(node.latency_ms))
        ? ` · ${Number(node.latency_ms).toFixed(0)}ms`
        : '';
    const tokens =
      node.token_usage || node.prompt_tokens || node.completion_tokens
        ? ` · tok ${Number(node.prompt_tokens || 0)}/${Number(node.completion_tokens || 0)}/${Number(node.token_usage || (Number(node.prompt_tokens || 0) + Number(node.completion_tokens || 0)))}`
        : '';
    const status = node.status && node.status !== 'ok' ? ` · ${node.status}` : '';
    const preview =
      short(node.output_preview || node.input_preview, 56) ||
      short(meta.message || meta.question, 56);

    const title = short(node.name || 'span', 40);
    const label = preview
      ? `${title}${intent}${tool}${latency}${tokens}${status}<br/>${preview}`
      : `${title}${intent}${tool}${latency}${tokens}${status}`;

    const cls = node.status === 'error' ? 'error' : kindClass(node.kind, node.name);
    lines.push(`  ${nodeShape(id, label, cls)}`);
    lines.push(`  class ${id} ${cls}`);
    if (parentId) {
      const edge = meta.intent ? `|${short(String(meta.intent), 18)}|` : '';
      lines.push(`  ${parentId} -->${edge} ${id}`);
    }
    for (const child of node.children || []) {
      walk(child, id);
    }
  };

  if (!tree?.length) {
    lines.push('  Empty(["No spans in this trace"])');
  } else {
    tree.forEach((root) => walk(root));
  }

  return lines.join('\n');
}

function flatten(tree: SpanNode[]): SpanNode[] {
  const out: SpanNode[] = [];
  const walk = (n: SpanNode) => {
    out.push(n);
    (n.children || []).forEach(walk);
  };
  tree.forEach(walk);
  return out;
}

export function TraceFlowDiagram({
  tree,
  onSelectSpan,
}: {
  tree: SpanNode[];
  onSelectSpan?: (span: SpanNode) => void;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const reactId = useId().replace(/:/g, '');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(true);
  const definition = useMemo(() => buildMermaid(tree), [tree]);
  const flat = useMemo(() => flatten(tree), [tree]);

  useEffect(() => {
    let cancelled = false;
    async function render() {
      if (!hostRef.current) return;
      setBusy(true);
      setError('');
      try {
        const { svg } = await mermaid.render(`traceFlow_${reactId}_${Date.now()}`, definition);
        if (cancelled || !hostRef.current) return;
        hostRef.current.innerHTML = svg;
        const svgEl = hostRef.current.querySelector('svg');
        if (svgEl) {
          svgEl.setAttribute('role', 'img');
          svgEl.setAttribute('aria-label', 'Trace execution flow diagram');
          svgEl.style.maxWidth = '100%';
          svgEl.style.height = 'auto';
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Failed to render flow diagram');
          if (hostRef.current) hostRef.current.innerHTML = '';
        }
      } finally {
        if (!cancelled) setBusy(false);
      }
    }
    render();
    return () => {
      cancelled = true;
    };
  }, [definition, reactId]);

  return (
    <div className="trace-flow">
      <div className="trace-flow-legend">
        <span className="legend-pill legend-span">Step</span>
        <span className="legend-pill legend-llm">LLM / route</span>
        <span className="legend-pill legend-tool">Tool</span>
        <span className="legend-pill legend-rag">RAG</span>
        <span className="legend-pill legend-hitl">HITL</span>
      </div>
      {busy ? <p className="muted">Rendering flow…</p> : null}
      {error ? <p className="alert alert-error">{error}</p> : null}
      <div className="trace-flow-canvas" ref={hostRef} />
      <details className="trace-flow-source">
        <summary>Mermaid source</summary>
        <pre className="pre compact">{definition}</pre>
      </details>
      {onSelectSpan && flat.length ? (
        <div className="trace-step-chips">
          <span className="muted">Jump to step:</span>
          {flat.map((s) => (
            <button
              key={s.span_id}
              type="button"
              className="trace-step-chip"
              onClick={() => onSelectSpan(s)}
              title={s.span_id}
            >
              {s.name || s.span_id}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function spanTimeline(tree: SpanNode[]): SpanNode[] {
  return flatten(tree);
}

import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { apiRequest } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { ChatMarkdown } from '../components/ChatMarkdown';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { useToast } from '../components/Toast';
import { Button, Pagination, TextArea } from '../components/ui';
import { usePagination } from '../hooks/usePagination';

interface ChatSession {
  session_id: string;
  title: string;
  updated_at?: string;
}

interface ChatMessage {
  id: number;
  role: string;
  content: string;
  intent?: string | null;
  metadata?: any;
  created_at?: string;
}

const SESSIONS_KEY = 'novacure.rag.sessionsOpen';

const SUGGESTIONS = [
  'What should we do for a packaging complaint on LOT-88392?',
  'Summarize quarantine steps for damaged packaging',
  'How do we triage a product quality complaint?',
];

export function RagPage() {
  const { user } = useAuth();
  const toast = useToast();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionId, setSessionId] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState('');
  const [result, setResult] = useState<any>(null);
  const [showDetails, setShowDetails] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [sessionsOpen, setSessionsOpen] = useState(() => {
    try {
      const stored = localStorage.getItem(SESSIONS_KEY);
      if (stored != null) return stored === '1';
    } catch {
      /* ignore */
    }
    return window.matchMedia('(min-width: 981px)').matches;
  });
  const sessionPager = usePagination(sessions, 8);
  const sources = result?.sources || [];
  const sourcePager = usePagination(sources, 5);
  const chatLogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      localStorage.setItem(SESSIONS_KEY, sessionsOpen ? '1' : '0');
    } catch {
      /* ignore */
    }
  }, [sessionsOpen]);

  useEffect(() => {
    const el = chatLogRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages.length, sessionId, busy]);

  async function refreshSessions(selectId?: string | null) {
    const list = await apiRequest<ChatSession[]>('/rag/sessions', {}, user?.access_token);
    setSessions(list);
    const preferred = selectId === null ? '' : selectId || sessionId;
    const next = preferred && list.some((s) => s.session_id === preferred) ? preferred : list[0]?.session_id || '';
    setSessionId(next);
    if (next) {
      const msgs = await apiRequest<ChatMessage[]>(
        `/rag/sessions/${next}/messages`,
        {},
        user?.access_token,
      );
      setMessages(msgs);
    } else {
      setMessages([]);
    }
  }

  useEffect(() => {
    if (!user?.access_token) return;
    refreshSessions().catch((e) => toast.error('Could not load chats', e.message));
  }, [user?.access_token]);

  async function createSession(select = true) {
    const s = await apiRequest<ChatSession>(
      '/rag/sessions',
      { method: 'POST', body: JSON.stringify({ title: 'Knowledge chat' }) },
      user?.access_token,
    );
    if (select) {
      await refreshSessions(s.session_id);
      setSessionsOpen(true);
    }
    return s.session_id;
  }

  async function confirmDeleteSession() {
    if (!pendingDeleteId) return;
    setDeleting(true);
    try {
      const id = pendingDeleteId;
      await apiRequest(`/rag/sessions/${id}`, { method: 'DELETE' }, user?.access_token);
      setResult(null);
      await refreshSessions(id === sessionId ? null : sessionId);
      toast.success('Chat deleted');
      setPendingDeleteId(null);
    } catch (err) {
      toast.error('Delete failed', err instanceof Error ? err.message : 'Please try again');
    } finally {
      setDeleting(false);
    }
  }

  async function ask(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    const optimisticId = -Date.now();
    setQuestion('');
    setMessages((prev) => [
      ...prev,
      { id: optimisticId, role: 'user', content: q },
    ]);
    setBusy(true);
    try {
      let active = sessionId;
      if (!active) {
        active = await createSession(false);
        setSessionId(active);
      }
      const data = await apiRequest(
        '/rag/query',
        {
          method: 'POST',
          body: JSON.stringify({ question: q, top_n: 5, session_id: active }),
        },
        user?.access_token,
      );
      setResult(data);
      setShowDetails(false);
      await refreshSessions(active);
    } catch (err) {
      setMessages((prev) => prev.filter((m) => m.id !== optimisticId));
      setQuestion(q);
      toast.error('Query failed', err instanceof Error ? err.message : 'Please try again');
    } finally {
      setBusy(false);
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    await ask(question);
  }

  const activeTitle = useMemo(
    () => sessions.find((s) => s.session_id === sessionId)?.title || 'Knowledge chat',
    [sessions, sessionId],
  );

  return (
    <div className="chat-page">
      <ConfirmDialog
        open={Boolean(pendingDeleteId)}
        title="Delete this chat?"
        message="This removes the conversation history from your account. This cannot be undone."
        confirmLabel="Delete chat"
        cancelLabel="Keep chat"
        tone="danger"
        busy={deleting}
        onCancel={() => {
          if (!deleting) setPendingDeleteId(null);
        }}
        onConfirm={() => {
          confirmDeleteSession().catch(() => undefined);
        }}
      />

      <div className={`chat-workspace ${sessionsOpen ? 'sessions-open' : 'sessions-closed'}`}>
        <button
          type="button"
          className="chat-sessions-backdrop"
          aria-label="Close sessions"
          tabIndex={sessionsOpen ? 0 : -1}
          onClick={() => setSessionsOpen(false)}
        />

        <aside className="chat-sessions" aria-hidden={!sessionsOpen}>
          <div className="chat-sessions-head">
            <div>
              <h2>Chats</h2>
              <p className="muted">{sessions.length ? `${sessions.length} recent` : 'Start a chat'}</p>
            </div>
            <div className="chat-sessions-actions">
              <Button
                variant="ghost"
                onClick={() => createSession().catch((e) => toast.error('Could not create chat', e.message))}
              >
                New
              </Button>
            </div>
          </div>

          <div className="session-list">
            {sessionPager.pageItems.map((s) => (
              <div
                key={s.session_id}
                className={`session-item ${s.session_id === sessionId ? 'active' : ''}`}
              >
                <button
                  type="button"
                  className="session-select"
                  onClick={() => {
                    setResult(null);
                    refreshSessions(s.session_id).catch((e) =>
                      toast.error('Could not open chat', e.message),
                    );
                    if (window.matchMedia('(max-width: 980px)').matches) setSessionsOpen(false);
                  }}
                >
                  <strong>{s.title || 'Knowledge chat'}</strong>
                </button>
                <button
                  type="button"
                  className="btn-session-delete"
                  aria-label="Delete chat"
                  title="Delete"
                  onClick={() => setPendingDeleteId(s.session_id)}
                >
                  ×
                </button>
              </div>
            ))}
            {!sessions.length ? (
              <p className="muted session-empty">No chats yet — ask a question below to begin.</p>
            ) : null}
          </div>

          <Pagination
            page={sessionPager.page}
            totalPages={sessionPager.totalPages}
            total={sessionPager.total}
            from={sessionPager.from}
            to={sessionPager.to}
            pageSize={sessionPager.pageSize}
            onPageChange={sessionPager.setPage}
            onPageSizeChange={sessionPager.setPageSize}
            pageSizeOptions={[5, 8, 12, 20]}
          />
        </aside>

        <section className={`chat-stage ${showDetails ? 'details-open' : ''}`}>
          <div className="chat-stage-bar">
            <button
              type="button"
              className={`icon-btn ${sessionsOpen ? 'is-active' : ''}`}
              aria-label={sessionsOpen ? 'Hide chats' : 'Show chats'}
              aria-pressed={sessionsOpen}
              onClick={() => setSessionsOpen((v) => !v)}
            >
              ☰
            </button>
            <div className="chat-stage-title">
              <strong>{activeTitle}</strong>
            </div>
            <Button
              variant="ghost"
              onClick={() => createSession().catch((e) => toast.error('Could not create chat', e.message))}
            >
              New chat
            </Button>
          </div>

          <div className="chat-stage-body">
            <div className="chat-log" ref={chatLogRef}>
              {messages.map((m) => (
                <div key={m.id} className={`chat-bubble chat-${m.role}`}>
                  <div className="chat-meta">
                    <span>{m.role === 'user' ? 'You' : m.role === 'assistant' ? 'Assistant' : m.role}</span>
                    {m.role === 'assistant' && m.intent ? (
                      <span className="chat-pill">{m.intent}</span>
                    ) : null}
                  </div>
                  <ChatMarkdown text={m.content} />
                </div>
              ))}
              {busy ? (
                <div className="chat-bubble chat-assistant" aria-live="polite" aria-label="Searching">
                  <div className="chat-typing">
                    <span /><span /><span />
                  </div>
                </div>
              ) : null}
              {!messages.length && !busy ? (
                <div className="chat-empty">
                  <p className="chat-empty-kicker">Knowledge query</p>
                  <strong>Ask about SOPs and training docs</strong>
                  <p className="muted">Answers stay grounded in indexed content. Try a starter below or type your own.</p>
                  <div className="chat-suggestions">
                    {SUGGESTIONS.map((s) => (
                      <button key={s} type="button" className="chat-chip" onClick={() => ask(s)}>
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>

            {result && !(result.sources || []).length ? (
              <div className="rag-insufficient" role="status">
                <strong>Insufficient evidence.</strong> No grounded SOP/chunks passed the rerank
                threshold for this question. Upload relevant docs in Admin Docs, or rephrase — the
                assistant will not invent clinical or regulatory guidance.
              </div>
            ) : null}

            <form className="chat-composer" onSubmit={onSubmit}>
              <div className="chat-composer-shell">
                <TextArea
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  rows={1}
                  required
                  aria-label="Question"
                  placeholder="Ask about SOPs, packaging, or intake guidance…"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      ask(question).catch(() => undefined);
                    }
                  }}
                />
                <Button type="submit" disabled={busy || !question.trim()}>
                  {busy ? 'Searching…' : 'Ask'}
                </Button>
              </div>
              <div className="chat-composer-meta">
                {result && (result.sources || []).length > 0 ? (
                  <button type="button" className="linkish" onClick={() => setShowDetails((v) => !v)}>
                    {showDetails ? 'Hide sources' : 'Show sources'}
                  </button>
                ) : (
                  <span className="muted chat-composer-hint">Enter to send · Shift+Enter for a new line</span>
                )}
              </div>
            </form>
          </div>

          {result && showDetails && (result.sources || []).length > 0 ? (
            <div className="chat-details-drawer" role="region" aria-label="Retrieval detail">
              <div className="chat-details-drawer-head">
                <h3>Retrieval detail</h3>
                <button type="button" className="linkish" onClick={() => setShowDetails(false)}>
                  Close
                </button>
              </div>
              <div className="chat-details">
                <h3>Query expansion</h3>
                <pre className="pre">{JSON.stringify(result.query_expansion, null, 2)}</pre>
                <h3>Sources</h3>
                <div className="scroll-panel chat-sources">
                  <ul>
                    {sourcePager.pageItems.map((s: any) => (
                      <li key={s.chunk_id}>
                        <strong>{s.doc_id}</strong> ({s.score?.toFixed?.(3)}
                        {s.rerank_method ? `, ${s.rerank_method}` : ''}) — {s.text}
                      </li>
                    ))}
                  </ul>
                </div>
                <Pagination
                  page={sourcePager.page}
                  totalPages={sourcePager.totalPages}
                  total={sourcePager.total}
                  from={sourcePager.from}
                  to={sourcePager.to}
                  pageSize={sourcePager.pageSize}
                  onPageChange={sourcePager.setPage}
                  onPageSizeChange={sourcePager.setPageSize}
                  pageSizeOptions={[5, 10, 20]}
                />
                <h3>Diagnostics</h3>
                <pre className="pre">{JSON.stringify(result.diagnostics, null, 2)}</pre>
              </div>
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}

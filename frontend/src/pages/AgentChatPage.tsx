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
  thread_id: string;
  updated_at?: string;
}

interface ChatMessage {
  id: number;
  role: string;
  content: string;
  intent?: string | null;
  created_at?: string;
}

const SESSIONS_KEY = 'novacure.agent.sessionsOpen';

const SUGGESTIONS = [
  'What should we do for packaging complaint LOT-88392?',
  'List recent intake reports',
  'Start the review of REF-2026-0001',
];

export function AgentChatPage() {
  const { user } = useAuth();
  const toast = useToast();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionId, setSessionId] = useState<string>('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
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
    const list = await apiRequest<ChatSession[]>('/agent/sessions', {}, user?.access_token);
    setSessions(list);
    const preferred = selectId === null ? '' : selectId || sessionId;
    const next = preferred && list.some((s) => s.session_id === preferred) ? preferred : list[0]?.session_id || '';
    setSessionId(next);
    if (next) {
      const msgs = await apiRequest<ChatMessage[]>(
        `/agent/sessions/${next}/messages`,
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
      '/agent/sessions',
      { method: 'POST', body: JSON.stringify({ title: 'New chat' }) },
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
      await apiRequest(`/agent/sessions/${id}`, { method: 'DELETE' }, user?.access_token);
      await refreshSessions(id === sessionId ? null : sessionId);
      toast.success('Chat deleted');
      setPendingDeleteId(null);
    } catch (err) {
      toast.error('Delete failed', err instanceof Error ? err.message : 'Please try again');
    } finally {
      setDeleting(false);
    }
  }

  async function sendMessage(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    const optimisticId = -Date.now();
    setInput('');
    setMessages((prev) => [
      ...prev,
      { id: optimisticId, role: 'user', content: message },
    ]);
    setBusy(true);
    try {
      let active = sessionId;
      if (!active) {
        active = await createSession(false);
        setSessionId(active);
      }
      const res = await apiRequest<any>(
        '/agent/chat',
        {
          method: 'POST',
          body: JSON.stringify({ session_id: active, message }),
        },
        user?.access_token,
      );
      if (res.interrupted) {
        toast.info('Approval needed', res.hitl?.hitl_request_id || 'Waiting for HITL approval');
      }
      await refreshSessions(active);
    } catch (err) {
      setMessages((prev) => prev.filter((m) => m.id !== optimisticId));
      setInput(message);
      toast.error('Chat failed', err instanceof Error ? err.message : 'Please try again');
    } finally {
      setBusy(false);
    }
  }

  async function send(e: FormEvent) {
    e.preventDefault();
    await sendMessage(input);
  }

  const activeTitle = useMemo(
    () => sessions.find((s) => s.session_id === sessionId)?.title || 'Agent chat',
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
                    refreshSessions(s.session_id).catch((e) =>
                      toast.error('Could not open chat', e.message),
                    );
                    if (window.matchMedia('(max-width: 980px)').matches) setSessionsOpen(false);
                  }}
                >
                  <strong>{s.title || 'Agent chat'}</strong>
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
              <p className="muted session-empty">No chats yet — send a message below to begin.</p>
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

        <section className="chat-stage">
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
                <div className="chat-bubble chat-assistant" aria-live="polite" aria-label="Working">
                  <div className="chat-typing">
                    <span /><span /><span />
                  </div>
                </div>
              ) : null}
              {!messages.length && !busy ? (
                <div className="chat-empty">
                  <p className="chat-empty-kicker">LangGraph agent</p>
                  <strong>Ready when you are</strong>
                  <p className="muted">Ask about intake, status changes, or SOP guidance. Approvals pause here when needed.</p>
                  <div className="chat-suggestions">
                    {SUGGESTIONS.map((s) => (
                      <button key={s} type="button" className="chat-chip" onClick={() => sendMessage(s)}>
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>

            <form className="chat-composer" onSubmit={send}>
              <div className="chat-composer-shell">
                <TextArea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  rows={1}
                  required
                  aria-label="Message"
                  placeholder="Message the agent…"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      sendMessage(input).catch(() => undefined);
                    }
                  }}
                />
                <Button type="submit" disabled={busy || !input.trim()}>
                  {busy ? 'Running…' : 'Send'}
                </Button>
              </div>
              <div className="chat-composer-meta">
                <p className="muted chat-composer-hint">Enter to send · Shift+Enter for a new line</p>
              </div>
            </form>
          </div>
        </section>
      </div>
    </div>
  );
}

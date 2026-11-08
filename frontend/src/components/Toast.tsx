import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

export type ToastTone = 'info' | 'success' | 'error';

export interface ToastItem {
  id: string;
  tone: ToastTone;
  title: string;
  message?: string;
}

interface ToastContextValue {
  push: (input: { tone?: ToastTone; title: string; message?: string; durationMs?: number }) => void;
  success: (title: string, message?: string) => void;
  info: (title: string, message?: string) => void;
  error: (title: string, message?: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

let toastSeq = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const timers = useRef<Map<string, number>>(new Map());

  const dismiss = useCallback((id: string) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
    const timer = timers.current.get(id);
    if (timer) {
      window.clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  const push = useCallback(
    ({
      tone = 'info',
      title,
      message,
      durationMs = 3800,
    }: {
      tone?: ToastTone;
      title: string;
      message?: string;
      durationMs?: number;
    }) => {
      const id = `toast-${++toastSeq}`;
      setItems((prev) => [...prev.slice(-4), { id, tone, title, message }]);
      if (durationMs > 0) {
        const timer = window.setTimeout(() => dismiss(id), durationMs);
        timers.current.set(id, timer);
      }
    },
    [dismiss],
  );

  useEffect(
    () => () => {
      timers.current.forEach((t) => window.clearTimeout(t));
      timers.current.clear();
    },
    [],
  );

  const value = useMemo<ToastContextValue>(
    () => ({
      push,
      success: (title, message) => push({ tone: 'success', title, message }),
      info: (title, message) => push({ tone: 'info', title, message }),
      error: (title, message) => push({ tone: 'error', title, message, durationMs: 5200 }),
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-host" aria-live="polite" aria-relevant="additions">
        {items.map((t) => (
          <div key={t.id} className={`toast toast-${t.tone}`} role="status">
            <div className={`toast-icon toast-icon-${t.tone}`} aria-hidden>
              {t.tone === 'success' ? '✓' : t.tone === 'error' ? '!' : 'i'}
            </div>
            <div className="toast-copy">
              <strong>{t.title}</strong>
              {t.message ? <p>{t.message}</p> : null}
            </div>
            <button type="button" className="toast-close" aria-label="Dismiss" onClick={() => dismiss(t.id)}>
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error('useToast must be used within ToastProvider');
  }
  return ctx;
}

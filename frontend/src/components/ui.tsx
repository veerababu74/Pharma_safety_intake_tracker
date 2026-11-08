import { useEffect, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react';

export function PageHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <header className="page-header">
      <h1>{title}</h1>
      {subtitle ? <p>{subtitle}</p> : null}
    </header>
  );
}

export function Modal({
  title,
  children,
  onClose,
  actions,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  actions?: ReactNode;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  return (
    <div className="modal-root" role="presentation">
      <button type="button" className="modal-backdrop" aria-label="Close dialog" onClick={onClose} />
      <div
        className="modal-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
      >
        <div className="modal-head">
          <h2 id="modal-title">{title}</h2>
          <button type="button" className="icon-btn" aria-label="Close" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {actions ? <div className="modal-actions">{actions}</div> : null}
      </div>
    </div>
  );
}

export function Pagination({
  page,
  totalPages,
  total,
  from,
  to,
  pageSize,
  onPageChange,
  onPageSizeChange,
  pageSizeOptions = [5, 10, 20, 50],
}: {
  page: number;
  totalPages: number;
  total: number;
  from: number;
  to: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  onPageSizeChange?: (size: number) => void;
  pageSizeOptions?: number[];
}) {
  if (total === 0 || totalPages <= 1) {
    return null;
  }
  return (
    <div className="pagination">
      <div className="pagination-meta muted">
        Showing {from}–{to} of {total}
      </div>
      <div className="pagination-controls">
        {onPageSizeChange ? (
          <label className="pagination-size">
            <span className="muted">Rows</span>
            <select
              className="input pagination-select"
              value={pageSize}
              onChange={(e) => onPageSizeChange(Number(e.target.value))}
            >
              {pageSizeOptions.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <Button variant="ghost" disabled={page <= 1} onClick={() => onPageChange(1)}>
          First
        </Button>
        <Button variant="ghost" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
          Prev
        </Button>
        <span className="pagination-page">
          Page {page} / {totalPages}
        </span>
        <Button variant="ghost" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>
          Next
        </Button>
        <Button variant="ghost" disabled={page >= totalPages} onClick={() => onPageChange(totalPages)}>
          Last
        </Button>
      </div>
    </div>
  );
}

export function Card({ title, children, actions }: { title?: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="card">
      {(title || actions) && (
        <div className="card-head">
          {title ? <h2>{title}</h2> : <span />}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function Button({
  variant = 'primary',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'ghost' | 'danger' }) {
  return <button className={`btn btn-${variant}`} {...props} />;
}

export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

export function TextInput({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={['input', className].filter(Boolean).join(' ')} {...props} />;
}

export function TextArea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={['input', 'textarea', className].filter(Boolean).join(' ')} {...props} />;
}

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={['input', className].filter(Boolean).join(' ')} {...props} />;
}

export function Alert({ tone = 'info', children }: { tone?: 'info' | 'error' | 'success'; children: ReactNode }) {
  return (
    <div className={`alert alert-${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <div className="alert-body">{children}</div>
    </div>
  );
}

export function Table({
  headers,
  rows,
  maxHeight,
}: {
  headers: string[];
  rows: ReactNode[][];
  maxHeight?: number | string;
}) {
  return (
    <div
      className={maxHeight != null ? 'table-wrap table-wrap-scroll' : 'table-wrap'}
      style={maxHeight != null ? { maxHeight } : undefined}
    >
      <table>
        <thead>
          <tr>
            {headers.map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={headers.length} className="muted">
                No data on this page.
              </td>
            </tr>
          ) : (
            rows.map((row, i) => (
              <tr key={i}>
                {row.map((cell, j) => (
                  <td key={j}>{cell}</td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export function StatusBadge({
  status,
  pendingClose,
}: {
  status: string;
  pendingClose?: boolean;
}) {
  const key = status.toLowerCase();
  const cls =
    key === 'new'
      ? 'badge-new'
      : key === 'closed'
        ? 'badge-closed'
        : key.includes('review')
          ? 'badge-review'
          : 'badge-pending';
  return (
    <span className={`badge ${pendingClose ? 'badge-pending' : cls}`}>
      {status}
      {pendingClose ? ' · pending close' : ''}
    </span>
  );
}

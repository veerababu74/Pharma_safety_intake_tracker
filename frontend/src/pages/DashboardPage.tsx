import { useEffect, useMemo, useState } from 'react';
import { apiRequest } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { NotesPromptModal } from '../components/NotesPromptModal';
import { ReportDetailModal } from '../components/ReportDetailModal';
import { useToast } from '../components/Toast';
import { Button, Card, Field, PageHeader, Pagination, Select, StatusBadge, Table } from '../components/ui';
import { usePagination } from '../hooks/usePagination';
import type { Report } from '../types';

type WorkflowPrompt =
  | { kind: 'start_review'; report: Report }
  | { kind: 'request_close'; report: Report }
  | null;

type DeletePrompt =
  | { kind: 'single'; report: Report }
  | { kind: 'bulk'; refs: string[] }
  | null;

export function DashboardPage() {
  const { user, hasRole } = useAuth();
  const toast = useToast();
  const [reports, setReports] = useState<Report[]>([]);
  const [status, setStatus] = useState('');
  const [reportType, setReportType] = useState('');
  const [viewRef, setViewRef] = useState<string | null>(null);
  const [prompt, setPrompt] = useState<WorkflowPrompt>(null);
  const [pendingDelete, setPendingDelete] = useState<DeletePrompt>(null);
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const pager = usePagination(reports, 10);
  const canTriage = hasRole('admin', 'reviewer');
  const canDelete = hasRole('admin');

  async function load() {
    const qs = new URLSearchParams();
    if (status) qs.set('status', status);
    if (reportType) qs.set('report_type', reportType);
    const data = await apiRequest<Report[]>(`/reports?${qs.toString()}`, {}, user?.access_token);
    setReports(data);
    setSelected((prev) => {
      const alive = new Set(data.map((r) => r.reference_id));
      const next = new Set<string>();
      for (const id of prev) {
        if (alive.has(id)) next.add(id);
      }
      return next;
    });
  }

  useEffect(() => {
    pager.setPage(1);
    setSelected(new Set());
    load().catch((e) => toast.error('Could not load reports', e.message));
  }, [status, reportType]);

  const counts = useMemo(() => {
    const base = { total: reports.length, new: 0, review: 0, closed: 0, pending: 0 };
    for (const r of reports) {
      if (r.pending_close) base.pending += 1;
      if (r.status === 'New') base.new += 1;
      else if (r.status === 'In Review') base.review += 1;
      else if (r.status === 'Closed') base.closed += 1;
    }
    return base;
  }, [reports]);

  const pageRefs = useMemo(
    () => pager.pageItems.map((r) => r.reference_id),
    [pager.pageItems],
  );
  const selectedOnPage = pageRefs.filter((id) => selected.has(id));
  const allPageSelected = pageRefs.length > 0 && selectedOnPage.length === pageRefs.length;
  const somePageSelected = selectedOnPage.length > 0 && !allPageSelected;

  function toggleOne(ref: string, checked: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (checked) next.add(ref);
      else next.delete(ref);
      return next;
    });
  }

  function togglePage(checked: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      for (const id of pageRefs) {
        if (checked) next.add(id);
        else next.delete(id);
      }
      return next;
    });
  }

  async function submitPrompt(notes: string) {
    if (!prompt) return;
    setBusy(true);
    try {
      if (prompt.kind === 'start_review') {
        await apiRequest(
          `/reports/${prompt.report.reference_id}/status`,
          {
            method: 'POST',
            body: JSON.stringify({
              new_status: 'In Review',
              reviewer_notes: notes || null,
            }),
          },
          user?.access_token,
        );
        toast.success('Review started', `${prompt.report.reference_id} is now In Review`);
      } else {
        await apiRequest(
          `/reports/${prompt.report.reference_id}/status`,
          {
            method: 'POST',
            body: JSON.stringify({
              new_status: 'Closed',
              reviewer_notes: notes,
            }),
          },
          user?.access_token,
        );
        toast.info('Close requested', `${prompt.report.reference_id} waiting for approver`);
      }
      setPrompt(null);
      await load();
    } catch (e) {
      toast.error('Update failed', e instanceof Error ? e.message : 'Please try again');
    } finally {
      setBusy(false);
    }
  }

  async function confirmDeleteReports() {
    if (!pendingDelete || !canDelete) return;
    setDeleting(true);
    const refs =
      pendingDelete.kind === 'single'
        ? [pendingDelete.report.reference_id]
        : pendingDelete.refs;
    try {
      const failures: string[] = [];
      for (const ref of refs) {
        try {
          await apiRequest(`/reports/${ref}`, { method: 'DELETE' }, user?.access_token);
        } catch {
          failures.push(ref);
        }
      }
      if (viewRef && refs.includes(viewRef) && !failures.includes(viewRef)) {
        setViewRef(null);
      }
      setPendingDelete(null);
      setSelected((prev) => {
        const next = new Set(prev);
        for (const ref of refs) {
          if (!failures.includes(ref)) next.delete(ref);
        }
        return next;
      });
      const ok = refs.length - failures.length;
      if (ok > 0) {
        toast.success(
          ok === 1 ? 'Report deleted' : `${ok} reports deleted`,
          failures.length ? `${failures.length} failed` : refs.length === 1 ? refs[0] : undefined,
        );
      }
      if (failures.length) {
        toast.error('Some deletes failed', failures.slice(0, 4).join(', '));
      }
      await load();
    } catch (e) {
      toast.error('Delete failed', e instanceof Error ? e.message : 'Please try again');
    } finally {
      setDeleting(false);
    }
  }

  const headers = useMemo(() => {
    const actionHeaders = ['REF', 'Type', 'Product', 'Lot', 'Status', 'Actions'];
    if (!canDelete) return actionHeaders;
    return [
      <span key="check" className="table-check">
        <input
          type="checkbox"
          aria-label="Select all reports on this page"
          checked={allPageSelected}
          ref={(el) => {
            if (el) el.indeterminate = somePageSelected;
          }}
          onChange={(e) => togglePage(e.target.checked)}
        />
      </span>,
      ...actionHeaders,
    ];
  }, [canDelete, allPageSelected, somePageSelected, pageRefs]);

  const rows = useMemo(
    () =>
      pager.pageItems.map((r) => {
        const actions = (
          <div className="row-actions row-actions-dashboard" key={`${r.reference_id}-act`}>
            <div className="row-actions-slot">
              <Button variant="ghost" onClick={() => setViewRef(r.reference_id)}>
                View
              </Button>
            </div>
            <div className="row-actions-slot">
              {canTriage && r.status === 'New' ? (
                <Button onClick={() => setPrompt({ kind: 'start_review', report: r })}>
                  Start Review
                </Button>
              ) : null}
              {canTriage && r.status === 'In Review' && !r.pending_close ? (
                <Button
                  variant="ghost"
                  onClick={() => setPrompt({ kind: 'request_close', report: r })}
                >
                  Request Close
                </Button>
              ) : null}
            </div>
            {canDelete ? (
              <div className="row-actions-slot">
                <Button
                  variant="danger"
                  onClick={() => setPendingDelete({ kind: 'single', report: r })}
                >
                  Delete
                </Button>
              </div>
            ) : (
              <div className="row-actions-slot" />
            )}
          </div>
        );

        const base = [
          <button
            key={`${r.reference_id}-ref`}
            type="button"
            className="linkish"
            title="View full report"
            onClick={() => setViewRef(r.reference_id)}
          >
            {r.reference_id}
          </button>,
          r.report_type,
          r.product_name,
          r.batch_lot_number,
          <StatusBadge key={`${r.reference_id}-st`} status={r.status} pendingClose={r.pending_close} />,
          actions,
        ];

        if (!canDelete) return base;

        return [
          <span key={`${r.reference_id}-chk`} className="table-check">
            <input
              type="checkbox"
              aria-label={`Select ${r.reference_id}`}
              checked={selected.has(r.reference_id)}
              onChange={(e) => toggleOne(r.reference_id, e.target.checked)}
            />
          </span>,
          ...base,
        ];
      }),
    [pager.pageItems, canTriage, canDelete, selected],
  );

  const deleteTitle =
    pendingDelete?.kind === 'bulk'
      ? `Delete ${pendingDelete.refs.length} reports?`
      : 'Delete this report?';
  const deleteMessage =
    pendingDelete?.kind === 'bulk'
      ? `Permanently remove ${pendingDelete.refs.length} selected reports. This cannot be undone.`
      : pendingDelete?.kind === 'single'
        ? `Permanently remove ${pendingDelete.report.reference_id} (${pendingDelete.report.product_name}, ${pendingDelete.report.batch_lot_number}). This cannot be undone.`
        : '';

  return (
    <div>
      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title={deleteTitle}
        message={deleteMessage}
        confirmLabel={pendingDelete?.kind === 'bulk' ? 'Delete selected' : 'Delete report'}
        cancelLabel="Keep"
        tone="danger"
        busy={deleting}
        onCancel={() => {
          if (!deleting) setPendingDelete(null);
        }}
        onConfirm={() => {
          confirmDeleteReports().catch(() => undefined);
        }}
      />
      <NotesPromptModal
        open={prompt?.kind === 'start_review'}
        title={`Start review — ${prompt?.report.reference_id || ''}`}
        message="Optional early triage notes. You can refine them when requesting close."
        label="Reviewer notes"
        placeholder="Initial checks, missing info, planned follow-up…"
        required={false}
        confirmLabel="Start review"
        busy={busy}
        onCancel={() => {
          if (!busy) setPrompt(null);
        }}
        onConfirm={(notes) => {
          submitPrompt(notes).catch(() => undefined);
        }}
      />
      <NotesPromptModal
        open={prompt?.kind === 'request_close'}
        title={`Request close — ${prompt?.report.reference_id || ''}`}
        message="Add triage details for the approver. Required before HITL close."
        label="Reviewer notes"
        placeholder="What you verified, findings, and why close is recommended…"
        required
        confirmLabel="Send to approver"
        busy={busy}
        onCancel={() => {
          if (!busy) setPrompt(null);
        }}
        onConfirm={(notes) => {
          submitPrompt(notes).catch(() => undefined);
        }}
      />

      <PageHeader title="Dashboard" subtitle="Filter and triage fictional intake reports" />

      <div className="stats-row">
        <div className="stat-card">
          <span className="label">Total</span>
          <span className="value">{counts.total}</span>
        </div>
        <div className="stat-card">
          <span className="label">New</span>
          <span className="value">{counts.new}</span>
        </div>
        <div className="stat-card">
          <span className="label">In Review</span>
          <span className="value">{counts.review}</span>
        </div>
        <div className="stat-card">
          <span className="label">Pending close</span>
          <span className="value">{counts.pending}</span>
        </div>
      </div>

      <Card title="Filters">
        <div className="form-row">
          <Field label="Status">
            <Select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All</option>
              <option>New</option>
              <option>In Review</option>
              <option>Closed</option>
            </Select>
          </Field>
          <Field label="Report type">
            <Select value={reportType} onChange={(e) => setReportType(e.target.value)}>
              <option value="">All</option>
              <option>Product Quality Complaint</option>
              <option>Suspected Adverse Event</option>
            </Select>
          </Field>
        </div>
      </Card>
      <Card title="Reports">
        {canDelete ? (
          <div className="bulk-bar">
            <span className="bulk-meta">
              {selected.size === 0
                ? 'Select rows to delete in bulk'
                : `${selected.size} selected`}
            </span>
            <div className="row-actions">
              <Button
                variant="ghost"
                disabled={selected.size === 0 || deleting}
                onClick={() => setSelected(new Set())}
              >
                Clear
              </Button>
              <Button
                variant="danger"
                disabled={selected.size === 0 || deleting}
                onClick={() =>
                  setPendingDelete({ kind: 'bulk', refs: Array.from(selected).sort() })
                }
              >
                Delete selected
              </Button>
            </div>
          </div>
        ) : null}
        <Table headers={headers} rows={rows} />
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

      <ReportDetailModal referenceId={viewRef} onClose={() => setViewRef(null)} />
    </div>
  );
}

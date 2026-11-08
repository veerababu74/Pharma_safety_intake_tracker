import { useEffect, useMemo, useState } from 'react';
import { apiRequest } from '../api/client';
import { useAuth } from '../auth/AuthContext';
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

export function DashboardPage() {
  const { user, hasRole } = useAuth();
  const toast = useToast();
  const [reports, setReports] = useState<Report[]>([]);
  const [status, setStatus] = useState('');
  const [reportType, setReportType] = useState('');
  const [viewRef, setViewRef] = useState<string | null>(null);
  const [prompt, setPrompt] = useState<WorkflowPrompt>(null);
  const [busy, setBusy] = useState(false);
  const pager = usePagination(reports, 10);
  const canTriage = hasRole('admin', 'reviewer');

  async function load() {
    const qs = new URLSearchParams();
    if (status) qs.set('status', status);
    if (reportType) qs.set('report_type', reportType);
    const data = await apiRequest<Report[]>(`/reports?${qs.toString()}`, {}, user?.access_token);
    setReports(data);
  }

  useEffect(() => {
    pager.setPage(1);
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

  const rows = useMemo(
    () =>
      pager.pageItems.map((r) => [
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
        <div className="row-actions" key={`${r.reference_id}-act`}>
          <Button variant="ghost" onClick={() => setViewRef(r.reference_id)}>
            View
          </Button>
          {canTriage && r.status === 'New' ? (
            <Button onClick={() => setPrompt({ kind: 'start_review', report: r })}>Start Review</Button>
          ) : null}
          {canTriage && r.status === 'In Review' && !r.pending_close ? (
            <Button variant="ghost" onClick={() => setPrompt({ kind: 'request_close', report: r })}>
              Request Close
            </Button>
          ) : null}
        </div>,
      ]),
    [pager.pageItems, canTriage],
  );

  return (
    <div>
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
        <Table headers={['REF', 'Type', 'Product', 'Lot', 'Status', 'Actions']} rows={rows} />
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

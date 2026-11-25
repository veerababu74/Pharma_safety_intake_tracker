import { useEffect, useState } from 'react';
import { apiRequest } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { HitlDetailModal, type HitlDetailItem } from '../components/HitlDetailModal';
import { NotesPromptModal } from '../components/NotesPromptModal';
import { ReportDetailModal } from '../components/ReportDetailModal';
import { useToast } from '../components/Toast';
import { Button, Card, PageHeader, Pagination, Table } from '../components/ui';
import { usePagination } from '../hooks/usePagination';
import type { Report } from '../types';

type ApprovePrompt =
  | { kind: 'report'; report: Report; approved: boolean }
  | { kind: 'agent'; item: HitlDetailItem; approved: boolean }
  | null;

export function ApprovalsPage() {
  const { user } = useAuth();
  const toast = useToast();
  const [reports, setReports] = useState<Report[]>([]);
  const [hitl, setHitl] = useState<HitlDetailItem[]>([]);
  const [viewRef, setViewRef] = useState<string | null>(null);
  const [viewHitl, setViewHitl] = useState<HitlDetailItem | null>(null);
  const [prompt, setPrompt] = useState<ApprovePrompt>(null);
  const [busy, setBusy] = useState(false);
  const hitlPager = usePagination(hitl, 8);
  const reportPager = usePagination(reports, 8);

  async function load() {
    const [allInReview, pendingHitl] = await Promise.all([
      apiRequest<Report[]>('/reports?status=In%20Review', {}, user?.access_token),
      apiRequest<HitlDetailItem[]>('/agent/hitl/pending', {}, user?.access_token).catch(() => []),
    ]);
    setReports(allInReview.filter((r) => r.pending_close));
    setHitl(pendingHitl);
    hitlPager.setPage(1);
    reportPager.setPage(1);
  }

  useEffect(() => {
    load().catch((e) => toast.error('Could not load approvals', e.message));
  }, []);

  async function submitDecision(comment: string) {
    if (!prompt) return;
    setBusy(true);
    try {
      if (prompt.kind === 'report') {
        const ref = prompt.report.reference_id;
        if (prompt.approved) {
          await apiRequest(
            `/reports/${ref}/approve-close`,
            { method: 'POST', body: JSON.stringify({ confirm: true, comment: comment || null }) },
            user?.access_token,
          );
          toast.success('Closed', ref);
        } else {
          await apiRequest(
            `/reports/${ref}/reject-close`,
            {
              method: 'POST',
              body: JSON.stringify({
                confirm: true,
                note: comment || 'Rejected by approver; remains In Review',
              }),
            },
            user?.access_token,
          );
          toast.info('Close rejected', `${ref} remains In Review`);
        }
      } else {
        const id = prompt.item.request_id;
        await apiRequest(
          `/agent/hitl/${id}/resolve`,
          {
            method: 'POST',
            body: JSON.stringify({
              approved: prompt.approved,
              note: comment || (prompt.approved ? undefined : 'Rejected by approver'),
            }),
          },
          user?.access_token,
        );
        toast[prompt.approved ? 'success' : 'info'](
          prompt.approved ? 'Approved' : 'Rejected',
          id,
        );
      }
      setPrompt(null);
      await load();
    } catch (e) {
      toast.error('Decision failed', e instanceof Error ? e.message : 'Please try again');
    } finally {
      setBusy(false);
    }
  }

  const activeRef =
    prompt?.kind === 'report'
      ? prompt.report.reference_id
      : prompt?.item.payload?.reference_id || prompt?.item.request_id || '';

  return (
    <div>
      <NotesPromptModal
        open={Boolean(prompt)}
        title={prompt?.approved ? `Approve close — ${activeRef}` : `Reject close — ${activeRef}`}
        message={
          prompt?.kind === 'report' && prompt.report.reviewer_notes
            ? `Reviewer notes: ${prompt.report.reviewer_notes}`
            : prompt?.kind === 'agent' &&
                (prompt.item.payload?.report?.reviewer_notes || prompt.item.payload?.reviewer_notes)
              ? `Reviewer notes: ${
                  prompt.item.payload?.report?.reviewer_notes || prompt.item.payload?.reviewer_notes
                }`
              : 'Optional comment is recorded with your decision.'
        }
        label="Approver comment"
        placeholder={
          prompt?.approved
            ? 'Optional: confirmation notes…'
            : 'Optional: why close is rejected…'
        }
        required={false}
        confirmLabel={prompt?.approved ? 'Approve close' : 'Reject'}
        busy={busy}
        onCancel={() => {
          if (!busy) setPrompt(null);
        }}
        onConfirm={(notes) => {
          submitDecision(notes).catch(() => undefined);
        }}
      />

      <HitlDetailModal
        item={viewHitl}
        onClose={() => setViewHitl(null)}
        onViewReport={(ref) => {
          setViewHitl(null);
          setViewRef(ref);
        }}
      />

      <PageHeader
        title="HITL Approvals"
        subtitle="Click a LangGraph HITL request to inspect details — reviewer notes shown on pending closes"
      />

      <Card title="Agent HITL (LangGraph checkpointer)">
        <Table
          headers={['Request', 'User', 'Tool', 'REF', 'Action']}
          rows={hitlPager.pageItems.map((h) => [
            <button
              key={`${h.request_id}-id`}
              type="button"
              className="linkish"
              onClick={() => setViewHitl(h)}
              title="View HITL details"
            >
              {h.request_id}
            </button>,
            h.username,
            h.tool_name,
            h.payload?.reference_id ? (
              <button
                key={`${h.request_id}-ref`}
                type="button"
                className="linkish"
                onClick={() => setViewHitl(h)}
              >
                {h.payload.reference_id}
              </button>
            ) : (
              '—'
            ),
            <div className="row-actions" key={h.request_id}>
              <Button variant="ghost" onClick={() => setViewHitl(h)}>
                Details
              </Button>
              <Button onClick={() => setPrompt({ kind: 'agent', item: h, approved: true })}>
                Approve
              </Button>
              <Button
                variant="danger"
                onClick={() => setPrompt({ kind: 'agent', item: h, approved: false })}
              >
                Reject
              </Button>
            </div>,
          ])}
        />
        <Pagination
          page={hitlPager.page}
          totalPages={hitlPager.totalPages}
          total={hitlPager.total}
          from={hitlPager.from}
          to={hitlPager.to}
          pageSize={hitlPager.pageSize}
          onPageChange={hitlPager.setPage}
          onPageSizeChange={hitlPager.setPageSize}
        />
      </Card>

      <Card title="Pending closes (from reviewers)">
        <Table
          headers={['REF', 'Product', 'Lot', 'Reviewer notes', 'Action']}
          rows={reportPager.pageItems.map((r) => [
            <button
              key={`${r.reference_id}-link`}
              type="button"
              className="linkish"
              onClick={() => setViewRef(r.reference_id)}
            >
              {r.reference_id}
            </button>,
            r.product_name,
            r.batch_lot_number,
            <span key={`${r.reference_id}-notes`} className="muted" title={r.reviewer_notes || ''}>
              {(r.reviewer_notes || '—').length > 80
                ? `${(r.reviewer_notes || '').slice(0, 80)}…`
                : r.reviewer_notes || '—'}
            </span>,
            <div className="row-actions" key={r.reference_id}>
              <Button variant="ghost" onClick={() => setViewRef(r.reference_id)}>
                View
              </Button>
              <Button onClick={() => setPrompt({ kind: 'report', report: r, approved: true })}>
                Approve Close
              </Button>
              <Button
                variant="danger"
                onClick={() => setPrompt({ kind: 'report', report: r, approved: false })}
              >
                Reject
              </Button>
            </div>,
          ])}
        />
        <Pagination
          page={reportPager.page}
          totalPages={reportPager.totalPages}
          total={reportPager.total}
          from={reportPager.from}
          to={reportPager.to}
          pageSize={reportPager.pageSize}
          onPageChange={reportPager.setPage}
          onPageSizeChange={reportPager.setPageSize}
        />
      </Card>

      <ReportDetailModal referenceId={viewRef} onClose={() => setViewRef(null)} />
    </div>
  );
}

import { useEffect, useState, type ReactNode } from 'react';
import { apiRequest } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import type { Report } from '../types';
import { Alert, Button, Modal, StatusBadge } from './ui';

function DetailRow({ label, value }: { label: string; value?: ReactNode }) {
  if (value == null || value === '') return null;
  return (
    <div className="detail-row">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

export function ReportDetailModal({
  referenceId,
  onClose,
}: {
  referenceId: string | null;
  onClose: () => void;
}) {
  const { user } = useAuth();
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!referenceId || !user?.access_token) {
      setReport(null);
      setError('');
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    let cancelled = false;
    setLoading(true);
    setError('');
    setReport(null);

    const timer = window.setTimeout(() => controller.abort(), 15000);
    apiRequest<Report>(
      `/reports/${encodeURIComponent(referenceId)}`,
      { signal: controller.signal },
      user.access_token,
    )
      .then((data) => {
        if (cancelled) return;
        if (!data || typeof data !== 'object' || !('reference_id' in data)) {
          setError('Unexpected response while loading report');
          setReport(null);
          return;
        }
        setReport(data);
      })
      .catch((e) => {
        if (cancelled) return;
        const msg =
          e?.name === 'AbortError'
            ? 'Timed out loading report — try again'
            : e instanceof Error
              ? e.message
              : 'Failed to load report';
        setError(msg);
        setReport(null);
      })
      .finally(() => {
        window.clearTimeout(timer);
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [referenceId, user?.access_token]);

  if (!referenceId) return null;

  return (
    <Modal
      title={report ? report.reference_id : referenceId}
      onClose={onClose}
      actions={
        <Button variant="ghost" onClick={onClose}>
          Close
        </Button>
      }
    >
      {loading ? <p className="muted">Loading report…</p> : null}
      {error ? <Alert tone="error">{error}</Alert> : null}
      {!loading && !error && !report ? (
        <p className="muted">No report data returned for {referenceId}.</p>
      ) : null}
      {report ? (
        <div className="report-detail">
          <div className="report-detail-head">
            <StatusBadge status={report.status} pendingClose={report.pending_close} />
            <span className="muted">{report.report_type}</span>
          </div>
          <dl className="detail-grid">
            <DetailRow label="Reference" value={report.reference_id} />
            <DetailRow label="Product" value={report.product_name} />
            <DetailRow label="Batch / lot" value={report.batch_lot_number} />
            <DetailRow label="Date received" value={report.date_received} />
            <DetailRow label="Reporter type" value={report.reporter_type} />
            <DetailRow label="Created by" value={report.created_by} />
            <DetailRow label="Updated by" value={report.updated_by || '—'} />
            <DetailRow label="Created at" value={report.created_at || '—'} />
            <DetailRow label="Updated at" value={report.updated_at || '—'} />
            <DetailRow
              label="Pending close"
              value={report.pending_close ? 'Yes — awaiting HITL approval' : 'No'}
            />
          </dl>
          <div className="detail-block">
            <h3>Description</h3>
            <pre className="pre">{report.description || '—'}</pre>
          </div>
          {report.event_description || report.event_onset_date ? (
            <div className="detail-block">
              <h3>Adverse event fields</h3>
              <dl className="detail-grid">
                <DetailRow label="Event onset" value={report.event_onset_date || '—'} />
              </dl>
              <pre className="pre">{report.event_description || '—'}</pre>
            </div>
          ) : null}
          {report.reviewer_notes ? (
            <div className="detail-block">
              <h3>Reviewer notes</h3>
              <pre className="pre">{report.reviewer_notes}</pre>
            </div>
          ) : null}
          {report.approver_comment ? (
            <div className="detail-block">
              <h3>Approver comment</h3>
              <pre className="pre">{report.approver_comment}</pre>
            </div>
          ) : null}
        </div>
      ) : null}
    </Modal>
  );
}

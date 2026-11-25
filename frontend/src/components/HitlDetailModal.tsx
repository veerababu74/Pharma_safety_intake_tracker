import { useEffect, useState } from 'react';
import { apiRequest } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import type { Report } from '../types';
import { Alert, Button, Modal, StatusBadge } from './ui';

export interface HitlDetailItem {
  request_id: string;
  session_id: string;
  thread_id?: string;
  username: string;
  tool_name: string;
  status: string;
  payload?: any;
  created_at?: string;
  resolution_note?: string | null;
  resolved_by?: string | null;
}

export function HitlDetailModal({
  item,
  onClose,
  onViewReport,
}: {
  item: HitlDetailItem | null;
  onClose: () => void;
  onViewReport?: (referenceId: string) => void;
}) {
  const { user } = useAuth();
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const referenceId = String(item?.payload?.reference_id || '').trim().toUpperCase() || null;
  const payloadReport = item?.payload?.report as Report | undefined;
  const reviewerNotes =
    payloadReport?.reviewer_notes ||
    item?.payload?.reviewer_notes ||
    report?.reviewer_notes ||
    null;

  useEffect(() => {
    if (!item || !referenceId || !user?.access_token) {
      setReport(payloadReport || null);
      setError('');
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    let cancelled = false;
    setLoading(true);
    setError('');
    // Prefer payload snapshot immediately so the modal isn't empty while fetching
    if (payloadReport) setReport(payloadReport);

    const timer = window.setTimeout(() => controller.abort(), 15000);
    apiRequest<Report>(`/reports/${referenceId}`, { signal: controller.signal }, user.access_token)
      .then((data) => {
        if (!cancelled) setReport(data);
      })
      .catch((e) => {
        if (cancelled) return;
        if (!payloadReport) {
          const msg =
            e?.name === 'AbortError'
              ? 'Timed out loading report details'
              : e instanceof Error
                ? e.message
                : 'Failed to load linked report';
          setError(msg);
        }
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
  }, [item?.request_id, referenceId, user?.access_token]);

  if (!item) return null;

  return (
    <Modal
      title={`HITL · ${item.request_id}`}
      onClose={onClose}
      actions={
        <>
          {referenceId && onViewReport ? (
            <Button
              variant="ghost"
              onClick={() => {
                onClose();
                onViewReport(referenceId);
              }}
            >
              Open full report
            </Button>
          ) : null}
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
        </>
      }
    >
      <div className="report-detail">
        <div className="report-detail-head">
          <StatusBadge status={item.status} />
          <span className="muted">{item.tool_name}</span>
        </div>
        <dl className="detail-grid">
          <div className="detail-row">
            <dt>Request</dt>
            <dd>{item.request_id}</dd>
          </div>
          <div className="detail-row">
            <dt>Requested by</dt>
            <dd>{item.username}</dd>
          </div>
          <div className="detail-row">
            <dt>Session</dt>
            <dd>{item.session_id}</dd>
          </div>
          {item.thread_id ? (
            <div className="detail-row">
              <dt>Thread</dt>
              <dd>{item.thread_id}</dd>
            </div>
          ) : null}
          <div className="detail-row">
            <dt>Reference</dt>
            <dd>{referenceId || '—'}</dd>
          </div>
          {item.created_at ? (
            <div className="detail-row">
              <dt>Created</dt>
              <dd>{item.created_at}</dd>
            </div>
          ) : null}
        </dl>

        {loading && !report ? <p className="muted">Loading linked report…</p> : null}
        {error ? <Alert tone="error">{error}</Alert> : null}

        {report ? (
          <>
            <div className="detail-block">
              <h3>Linked report</h3>
              <dl className="detail-grid">
                <div className="detail-row">
                  <dt>Product</dt>
                  <dd>{report.product_name}</dd>
                </div>
                <div className="detail-row">
                  <dt>Lot</dt>
                  <dd>{report.batch_lot_number}</dd>
                </div>
                <div className="detail-row">
                  <dt>Type</dt>
                  <dd>{report.report_type}</dd>
                </div>
                <div className="detail-row">
                  <dt>Status</dt>
                  <dd>
                    <StatusBadge status={report.status} pendingClose={report.pending_close} />
                  </dd>
                </div>
              </dl>
              <pre className="pre">{report.description || '—'}</pre>
            </div>
          </>
        ) : null}

        {reviewerNotes ? (
          <div className="detail-block">
            <h3>Reviewer notes</h3>
            <pre className="pre">{reviewerNotes}</pre>
          </div>
        ) : (
          <p className="muted">No reviewer notes attached to this HITL payload.</p>
        )}

        {item.payload && !payloadReport ? (
          <div className="detail-block">
            <h3>Raw HITL payload</h3>
            <pre className="pre">{JSON.stringify(item.payload, null, 2)}</pre>
          </div>
        ) : null}
      </div>
    </Modal>
  );
}

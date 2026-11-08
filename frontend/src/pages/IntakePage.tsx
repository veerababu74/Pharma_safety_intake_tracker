import { FormEvent, useState } from 'react';
import { apiRequest } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { ReportDetailModal } from '../components/ReportDetailModal';
import { useToast } from '../components/Toast';
import { Button, Card, Field, PageHeader, Select, TextArea, TextInput } from '../components/ui';

const REPORT_PRESETS = ['Product Quality Complaint', 'Suspected Adverse Event'] as const;
const REPORTER_PRESETS = ['Consumer', 'Healthcare Professional', 'Pharmacist', 'Wholesaler'] as const;

type FieldKey =
  | 'report_type'
  | 'reporter_type'
  | 'product_name'
  | 'batch_lot_number'
  | 'date_received'
  | 'description'
  | 'event_description'
  | 'event_onset_date';

const FIELD_HINTS: Record<FieldKey, string> = {
  report_type: 'Choose a preset or enter a custom report type.',
  reporter_type: 'Choose a preset or enter a custom reporter type.',
  product_name: 'Product name is required.',
  batch_lot_number: 'Batch/lot must match LOT-##### (five digits).',
  date_received: 'Date received is required.',
  description: 'Description is required.',
  event_description: 'Event description is required for Suspected Adverse Event.',
  event_onset_date: 'Event onset date is required for Suspected Adverse Event.',
};

function parseFieldErrors(message: string): Partial<Record<FieldKey, string>> {
  const out: Partial<Record<FieldKey, string>> = {};
  const parts = message.split(';').map((p) => p.trim()).filter(Boolean);
  for (const part of parts) {
    const lower = part.toLowerCase();
    (Object.keys(FIELD_HINTS) as FieldKey[]).forEach((key) => {
      if (lower.includes(key) || lower.startsWith(key.replace(/_/g, ' '))) {
        out[key] = part;
      }
    });
    if (lower.includes('lot-#####') || lower.includes('batch_lot')) {
      out.batch_lot_number = part;
    }
  }
  return out;
}

export function IntakePage() {
  const { user } = useAuth();
  const [reportPreset, setReportPreset] = useState<string>('Product Quality Complaint');
  const [customReportType, setCustomReportType] = useState('');
  const [reporterPreset, setReporterPreset] = useState<string>('Consumer');
  const [customReporterType, setCustomReporterType] = useState('');
  const [form, setForm] = useState({
    product_name: 'NeuroCalm 50mg',
    batch_lot_number: 'LOT-88392',
    date_received: new Date().toISOString().slice(0, 10),
    description: 'Bottle seal was broken on arrival (fictional).',
    event_description: '',
    event_onset_date: '',
  });
  const toast = useToast();
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<FieldKey, string>>>({});
  const [savedRef, setSavedRef] = useState<string | null>(null);
  const [viewRef, setViewRef] = useState<string | null>(null);

  const reportType =
    reportPreset === '__custom__' ? customReportType.trim() : reportPreset;
  const reporterType =
    reporterPreset === '__custom__' ? customReporterType.trim() : reporterPreset;
  const showAeFields =
    reportType.toLowerCase().includes('adverse') || reportPreset === 'Suspected Adverse Event';

  function validateClient(): Partial<Record<FieldKey, string>> {
    const next: Partial<Record<FieldKey, string>> = {};
    if (!reportType) next.report_type = FIELD_HINTS.report_type;
    if (!reporterType) next.reporter_type = FIELD_HINTS.reporter_type;
    if (!form.product_name.trim()) next.product_name = FIELD_HINTS.product_name;
    if (!form.batch_lot_number.trim()) next.batch_lot_number = FIELD_HINTS.batch_lot_number;
    else if (!/^LOT-\d{5}$/.test(form.batch_lot_number.trim())) {
      next.batch_lot_number = FIELD_HINTS.batch_lot_number;
    }
    if (!form.date_received) next.date_received = FIELD_HINTS.date_received;
    if (!form.description.trim()) next.description = FIELD_HINTS.description;
    if (showAeFields) {
      if (!form.event_description.trim()) next.event_description = FIELD_HINTS.event_description;
      if (!form.event_onset_date) next.event_onset_date = FIELD_HINTS.event_onset_date;
    }
    return next;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const clientErrors = validateClient();
    setFieldErrors(clientErrors);
    if (Object.keys(clientErrors).length) {
      toast.error('Fix highlighted fields', 'Check the form and submit again.');
      return;
    }
    try {
      const payload = {
        report_type: reportType,
        reporter_type: reporterType,
        product_name: form.product_name,
        batch_lot_number: form.batch_lot_number,
        date_received: form.date_received,
        description: form.description,
        event_description: showAeFields ? form.event_description : null,
        event_onset_date: showAeFields ? form.event_onset_date : null,
      };
      const created = await apiRequest<{ reference_id: string }>(
        '/reports',
        { method: 'POST', body: JSON.stringify(payload) },
        user?.access_token,
      );
      setFieldErrors({});
      setSavedRef(created.reference_id);
      toast.success('Report saved', created.reference_id);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Save failed';
      toast.error('Save failed', msg);
      setFieldErrors(parseFieldErrors(msg));
    }
  }

  function fieldClass(key: FieldKey): string | undefined {
    return fieldErrors[key] ? 'has-error' : undefined;
  }

  return (
    <div>
      <PageHeader title="Intake Form" subtitle="Create fictional PQC, AE, or custom report types" />
      {savedRef ? (
        <div className="row-actions" style={{ marginBottom: '1rem' }}>
          <Button onClick={() => setViewRef(savedRef)}>View submitted report</Button>
        </div>
      ) : null}
      <Card title="New report">
        <form className="form-grid" onSubmit={onSubmit}>
          <Field label="Report type">
            <Select
              className={fieldClass('report_type')}
              value={reportPreset}
              onChange={(e) => setReportPreset(e.target.value)}
            >
              {REPORT_PRESETS.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
              <option value="__custom__">Custom (type your own)…</option>
            </Select>
            {fieldErrors.report_type ? <span className="field-error">{fieldErrors.report_type}</span> : null}
          </Field>
          {reportPreset === '__custom__' ? (
            <Field label="Custom report type">
              <TextInput
                className={fieldClass('report_type')}
                value={customReportType}
                onChange={(e) => setCustomReportType(e.target.value)}
                placeholder="e.g. Medical Information Inquiry"
              />
            </Field>
          ) : null}

          <Field label="Product name">
            <TextInput
              className={fieldClass('product_name')}
              value={form.product_name}
              onChange={(e) => setForm({ ...form, product_name: e.target.value })}
            />
            {fieldErrors.product_name ? <span className="field-error">{fieldErrors.product_name}</span> : null}
          </Field>
          <Field label="Batch / Lot (LOT-#####)">
            <TextInput
              className={fieldClass('batch_lot_number')}
              value={form.batch_lot_number}
              onChange={(e) => setForm({ ...form, batch_lot_number: e.target.value })}
            />
            {fieldErrors.batch_lot_number ? (
              <span className="field-error">{fieldErrors.batch_lot_number}</span>
            ) : null}
          </Field>
          <Field label="Date received">
            <TextInput
              className={fieldClass('date_received')}
              type="date"
              value={form.date_received}
              onChange={(e) => setForm({ ...form, date_received: e.target.value })}
            />
            {fieldErrors.date_received ? <span className="field-error">{fieldErrors.date_received}</span> : null}
          </Field>

          <Field label="Reporter type">
            <Select
              className={fieldClass('reporter_type')}
              value={reporterPreset}
              onChange={(e) => setReporterPreset(e.target.value)}
            >
              {REPORTER_PRESETS.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
              <option value="__custom__">Custom (type your own)…</option>
            </Select>
            {fieldErrors.reporter_type ? <span className="field-error">{fieldErrors.reporter_type}</span> : null}
          </Field>
          {reporterPreset === '__custom__' ? (
            <Field label="Custom reporter type">
              <TextInput
                className={fieldClass('reporter_type')}
                value={customReporterType}
                onChange={(e) => setCustomReporterType(e.target.value)}
                placeholder="e.g. Call Center Agent"
              />
            </Field>
          ) : null}

          <Field label="Description">
            <TextArea
              className={fieldClass('description')}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
            {fieldErrors.description ? <span className="field-error">{fieldErrors.description}</span> : null}
          </Field>
          {showAeFields && (
            <>
              <Field label="Event description">
                <TextInput
                  className={fieldClass('event_description')}
                  value={form.event_description}
                  onChange={(e) => setForm({ ...form, event_description: e.target.value })}
                />
                {fieldErrors.event_description ? (
                  <span className="field-error">{fieldErrors.event_description}</span>
                ) : null}
              </Field>
              <Field label="Event onset date">
                <TextInput
                  className={fieldClass('event_onset_date')}
                  type="date"
                  value={form.event_onset_date}
                  onChange={(e) => setForm({ ...form, event_onset_date: e.target.value })}
                />
                {fieldErrors.event_onset_date ? (
                  <span className="field-error">{fieldErrors.event_onset_date}</span>
                ) : null}
              </Field>
            </>
          )}
          <Button type="submit">Submit report</Button>
        </form>
      </Card>
      <ReportDetailModal referenceId={viewRef} onClose={() => setViewRef(null)} />
    </div>
  );
}

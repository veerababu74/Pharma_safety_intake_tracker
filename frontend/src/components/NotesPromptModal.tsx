import { useEffect, useState } from 'react';
import { Button, Modal, TextArea } from './ui';

/** Small modal to collect required/optional notes before a workflow action. */
export function NotesPromptModal({
  open,
  title,
  message,
  label,
  placeholder,
  required = false,
  confirmLabel = 'Continue',
  cancelLabel = 'Cancel',
  busy = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  message?: string;
  label: string;
  placeholder?: string;
  required?: boolean;
  confirmLabel?: string;
  cancelLabel?: string;
  busy?: boolean;
  onConfirm: (notes: string) => void;
  onCancel: () => void;
}) {
  const [notes, setNotes] = useState('');

  useEffect(() => {
    if (open) setNotes('');
  }, [open]);

  if (!open) return null;

  const trimmed = notes.trim();
  const canSubmit = !required || trimmed.length > 0;

  return (
    <Modal
      title={title}
      onClose={() => {
        if (!busy) onCancel();
      }}
      actions={
        <>
          <Button variant="ghost" onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </Button>
          <Button
            disabled={busy || !canSubmit}
            onClick={() => onConfirm(trimmed)}
          >
            {busy ? 'Working…' : confirmLabel}
          </Button>
        </>
      }
    >
      {message ? <p className="muted" style={{ marginTop: 0 }}>{message}</p> : null}
      <label className="field">
        <span>
          {label}
          {required ? ' *' : ' (optional)'}
        </span>
        <TextArea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={4}
          placeholder={placeholder}
          required={required}
          autoFocus
        />
      </label>
    </Modal>
  );
}

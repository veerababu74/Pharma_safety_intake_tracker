import { FormEvent, useEffect, useState } from 'react';
import { apiRequest } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { useToast } from '../components/Toast';
import { Button, Card, Field, PageHeader, Pagination, Select, Table, TextInput } from '../components/ui';
import { usePagination } from '../hooks/usePagination';
import type { RagDocument } from '../types';

export function AdminDocsPage() {
  const { user } = useAuth();
  const toast = useToast();
  const [docs, setDocs] = useState<RagDocument[]>([]);
  const [strategies, setStrategies] = useState<string[]>([]);
  const [title, setTitle] = useState('');
  const [sourceType, setSourceType] = useState('SOP');
  const [sourcePreset, setSourcePreset] = useState('SOP');
  const [customSource, setCustomSource] = useState('');
  const [chunkStrategy, setChunkStrategy] = useState('recursive');
  const [chunkSize, setChunkSize] = useState(512);
  const [chunkOverlap, setChunkOverlap] = useState(64);
  const [file, setFile] = useState<File | null>(null);
  const [pendingDelete, setPendingDelete] = useState<RagDocument | null>(null);
  const [deleting, setDeleting] = useState(false);
  const pager = usePagination(docs, 8);

  async function refresh() {
    const [list, meta] = await Promise.all([
      apiRequest<RagDocument[]>('/rag/documents', {}, user?.access_token),
      apiRequest<{ strategies: string[]; defaults: any }>('/rag/chunk-strategies', {}, user?.access_token),
    ]);
    setDocs(list);
    setStrategies(meta.strategies);
    setChunkStrategy(meta.defaults.strategy);
    setChunkSize(meta.defaults.chunk_size);
    setChunkOverlap(meta.defaults.chunk_overlap);
  }

  useEffect(() => {
    refresh().catch((e) => toast.error('Could not load documents', e.message));
  }, []);

  async function onUpload(e: FormEvent) {
    e.preventDefault();
    if (!file) {
      toast.error('Choose a file', 'Pick a PDF, TXT, MD, DOCX, or CSV to index.');
      return;
    }
    const body = new FormData();
    const resolvedSource =
      sourcePreset === '__custom__' ? customSource.trim() || 'Custom' : sourcePreset || sourceType;
    body.append('title', title || file.name);
    body.append('source_type', resolvedSource);
    body.append('chunk_strategy', chunkStrategy);
    body.append('chunk_size', String(chunkSize));
    body.append('chunk_overlap', String(chunkOverlap));
    body.append('file', file);
    try {
      const res = await apiRequest<{ doc_id: string; chunk_count: number }>(
        '/rag/documents',
        { method: 'POST', body },
        user?.access_token,
      );
      toast.success('Document indexed', `${res.doc_id} · ${res.chunk_count} chunks`);
      setFile(null);
      await refresh();
    } catch (err) {
      toast.error('Upload failed', err instanceof Error ? err.message : 'Please try again');
    }
  }

  async function confirmDeleteDoc() {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await apiRequest(`/rag/documents/${pendingDelete.doc_id}`, { method: 'DELETE' }, user?.access_token);
      toast.success('Document deleted', `${pendingDelete.doc_id} removed from storage + vectors`);
      setPendingDelete(null);
      await refresh();
    } catch (err) {
      toast.error('Delete failed', err instanceof Error ? err.message : 'Please try again');
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div>
      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="Delete this document?"
        message={
          pendingDelete
            ? `${pendingDelete.title || pendingDelete.doc_id} will be removed from storage and the vector index.`
            : ''
        }
        confirmLabel="Delete document"
        cancelLabel="Keep document"
        tone="danger"
        busy={deleting}
        onCancel={() => {
          if (!deleting) setPendingDelete(null);
        }}
        onConfirm={() => {
          confirmDeleteDoc().catch(() => undefined);
        }}
      />

      <PageHeader
        title="Admin Document Injection"
        subtitle="Upload PDF/TXT/DOCX/CSV via LangChain loaders, choose chunking, view or delete (storage + vectors)"
      />

      <Card title="Ingest document">
        <form className="form-grid" onSubmit={onUpload}>
          <Field label="Title">
            <TextInput value={title} onChange={(e) => setTitle(e.target.value)} placeholder="SOP title" />
          </Field>
          <Field label="Source type">
            <Select
              value={sourcePreset}
              onChange={(e) => {
                const v = e.target.value;
                setSourcePreset(v);
                if (v !== '__custom__') {
                  setSourceType(v);
                  setCustomSource('');
                }
              }}
            >
              <option value="SOP">SOP</option>
              <option value="Past Report Digest">Past Report Digest</option>
              <option value="Solution Knowledge">Solution Knowledge</option>
              <option value="Training Note">Training Note</option>
              <option value="__custom__">Custom (type your own)…</option>
            </Select>
          </Field>
          {sourcePreset === '__custom__' ? (
            <Field label="Custom source name">
              <TextInput
                value={customSource}
                onChange={(e) => {
                  setCustomSource(e.target.value);
                  setSourceType(e.target.value);
                }}
                placeholder="e.g. Packaging CAPA Playbook"
                required
              />
            </Field>
          ) : null}
          <Field label="Chunking strategy">
            <Select value={chunkStrategy} onChange={(e) => setChunkStrategy(e.target.value)}>
              {strategies.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </Field>
          <p className="muted">
            <strong>semantic</strong> uses the configured embedding model (cosine topic breaks).{' '}
            <strong>agentic</strong> uses the configured LLM to propose topic segments.
          </p>
          <Field label="Chunk size">
            <TextInput
              type="number"
              value={chunkSize}
              onChange={(e) => setChunkSize(Number(e.target.value))}
              min={50}
            />
          </Field>
          <Field label="Chunk overlap">
            <TextInput
              type="number"
              value={chunkOverlap}
              onChange={(e) => setChunkOverlap(Number(e.target.value))}
              min={0}
            />
          </Field>
          <Field label="File (pdf, txt, md, docx, csv — LangChain loaders)">
            <input
              type="file"
              accept=".pdf,.txt,.md,.docx,.csv,application/pdf,text/plain,text/csv,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
          </Field>
          <Button type="submit">Upload & index</Button>
        </form>
      </Card>

      <Card title="Indexed documents">
        <Table
          headers={['Doc ID', 'Title', 'Strategy', 'Chunks', 'Actions']}
          rows={pager.pageItems.map((d) => [
            d.doc_id,
            d.title,
            `${d.chunk_strategy} (${d.chunk_size}/${d.chunk_overlap})`,
            d.chunk_count,
            <div className="row-actions" key={d.doc_id}>
              <Button
                variant="ghost"
                onClick={async () => {
                  try {
                    const blob = await apiRequest<Blob>(
                      `/rag/documents/${d.doc_id}/content`,
                      {},
                      user?.access_token,
                    );
                    const url = URL.createObjectURL(blob as Blob);
                    window.open(url, '_blank');
                  } catch (err) {
                    toast.error('View failed', err instanceof Error ? err.message : 'Please try again');
                  }
                }}
              >
                View
              </Button>
              <Button variant="danger" onClick={() => setPendingDelete(d)}>
                Delete
              </Button>
            </div>,
          ])}
        />
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
    </div>
  );
}

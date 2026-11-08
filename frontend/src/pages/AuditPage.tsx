import { useEffect, useState } from 'react';
import { apiRequest } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { useToast } from '../components/Toast';
import { Button, Card, PageHeader, Pagination, Table } from '../components/ui';
import { usePagination } from '../hooks/usePagination';

export function AuditPage() {
  const { user } = useAuth();
  const toast = useToast();
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const pager = usePagination(logs, 15);

  async function load() {
    if (!user?.access_token) return;
    setLoading(true);
    try {
      const data = await apiRequest<any[]>('/audit/logs?limit=200', {}, user.access_token);
      setLogs(Array.isArray(data) ? data : []);
    } catch (e: any) {
      toast.error('Could not load audit logs', e.message || 'Please try again');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [user?.access_token]);

  return (
    <div>
      <PageHeader title="Audit Trail" subtitle="Immutable local audit events (separate SQLite)" />
      <Card
        title={`Recent audit events (${logs.length})`}
        actions={
          <Button variant="ghost" onClick={() => load()} disabled={loading}>
            Refresh
          </Button>
        }
      >
        {!logs.length ? (
          <p className="muted">No audit events yet. Browse the app, then refresh.</p>
        ) : (
          <>
            <div className="scroll-panel">
              <Table
                headers={['Time', 'Actor', 'Method', 'Path', 'Status', 'Details']}
                rows={pager.pageItems.map((l) => [
                  l.timestamp || '—',
                  `${l.actor || '—'}${l.role ? ` (${l.role})` : ''}`,
                  l.method || l.action || '—',
                  l.path || l.resource_id || '—',
                  l.status_code ?? '—',
                  l.details || '—',
                ])}
              />
            </div>
            <Pagination
              page={pager.page}
              totalPages={pager.totalPages}
              total={pager.total}
              from={pager.from}
              to={pager.to}
              pageSize={pager.pageSize}
              onPageChange={pager.setPage}
              onPageSizeChange={pager.setPageSize}
              pageSizeOptions={[10, 15, 25, 50]}
            />
          </>
        )}
      </Card>
    </div>
  );
}

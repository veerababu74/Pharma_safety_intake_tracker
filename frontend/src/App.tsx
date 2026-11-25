import { Navigate, Route, Routes } from 'react-router-dom';
import { useAuth } from './auth/AuthContext';
import { AppShell } from './components/AppShell';
import { AdminDocsPage } from './pages/AdminDocsPage';
import { AgentChatPage } from './pages/AgentChatPage';
import { ApprovalsPage } from './pages/ApprovalsPage';
import { AuditPage } from './pages/AuditPage';
import { DashboardPage } from './pages/DashboardPage';
import { IntakePage } from './pages/IntakePage';
import { LoginPage } from './pages/LoginPage';
import { ObservabilityPage } from './pages/ObservabilityPage';
import { RagPage } from './pages/RagPage';
import type { Role } from './types';

function Protected({ children, roles }: { children: React.ReactNode; roles?: Role[] }) {
  const { user, hasRole } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (roles && !hasRole(...roles)) return <Navigate to="/" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <Protected>
            <AppShell />
          </Protected>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route
          path="intake"
          element={
            <Protected roles={['admin', 'reviewer', 'operator']}>
              <IntakePage />
            </Protected>
          }
        />
        <Route
          path="approvals"
          element={
            <Protected roles={['admin', 'approver']}>
              <ApprovalsPage />
            </Protected>
          }
        />
        <Route path="agent" element={<AgentChatPage />} />
        <Route path="rag" element={<RagPage />} />
        <Route
          path="admin/docs"
          element={
            <Protected roles={['admin']}>
              <AdminDocsPage />
            </Protected>
          }
        />
        <Route
          path="observability"
          element={
            <Protected roles={['admin', 'reviewer']}>
              <ObservabilityPage />
            </Protected>
          }
        />
        <Route
          path="audit"
          element={
            <Protected roles={['admin', 'reviewer', 'approver']}>
              <AuditPage />
            </Protected>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
